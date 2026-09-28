"""
External medicine knowledge adapters.

The external layer is intentionally advisory:
- Local curated knowledge remains the highest-trust source.
- RxNorm provides standardized terminology and candidate discovery.
- RxNorm lexical scores are NOT treated as percentage confidence.
- External candidates must never automatically become clinically verified.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from urllib.parse import quote
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

RXNORM_BASE_URL = "https://rxnav.nlm.nih.gov/REST"

DEFAULT_TIMEOUT_SECONDS = 3.0
DEFAULT_TOP_K = 5

# =========================================================
# In-process external lookup cache
#
# Prevents repeated live RxNorm calls for the same medicine
# text within a single process/worker lifetime.
#
# Cache design:
#   key   = (normalised_text, top_k)
#   value = (result_list, inserted_at_monotonic_seconds)
#
# TTL: 1 hour.  Entries are evicted lazily on access.
# Cache is bounded to EXTERNAL_CACHE_MAX_SIZE entries.
# No persistence — the in-process cache is purely advisory.
# =========================================================

_EXTERNAL_CACHE_TTL_SECONDS = 3600  # 1 hour
_EXTERNAL_CACHE_MAX_SIZE = 1000

_external_cache: dict[
    tuple[str, int],
    tuple[list[dict], float],
] = {}
_external_cache_lock = threading.Lock()


def _cache_get(
    key: tuple[str, int],
) -> list[dict] | None:
    with _external_cache_lock:
        entry = _external_cache.get(key)
        if entry is None:
            return None
        result, inserted_at = entry
        age = time.monotonic() - inserted_at
        if age > _EXTERNAL_CACHE_TTL_SECONDS:
            del _external_cache[key]
            return None
        return result


def _cache_put(
    key: tuple[str, int],
    result: list[dict],
) -> None:
    with _external_cache_lock:
        # Evict oldest entries when the cache is full.
        if len(_external_cache) >= _EXTERNAL_CACHE_MAX_SIZE:
            oldest_key = min(
                _external_cache,
                key=lambda k: _external_cache[k][1],
            )
            del _external_cache[oldest_key]
        _external_cache[key] = (result, time.monotonic())


def clear_external_lookup_cache() -> None:
    """
    Clear the in-process external lookup cache.

    Useful in tests and after bulk vocabulary import to ensure
    fresh external lookups are made.
    """
    with _external_cache_lock:
        _external_cache.clear()

# RxNorm's approximate-match score is a lexical ranking signal, not
# a normalized probability. We therefore use rank + score ordering
# to derive a conservative bounded evidence value.
MAX_EXTERNAL_SOURCE_CONFIDENCE = 0.74


def _http_get_json(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    """Fetch JSON from an external endpoint, failing closed."""

    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "PrescriptionIntelligence/1.0",
        },
        method="GET",
    )

    with urlopen(request, timeout=timeout) as response:
        payload = response.read().decode("utf-8")

    return json.loads(payload)


def _safe_float(value: object) -> float:
    """
    Safely convert a value to float.

    Invalid or missing values return 0.0 so callers and tests can
    safely perform numeric comparisons without handling None.
    """

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _normalize_match_text(value: object) -> str:
    """
    Normalize text for comparison while preserving medicine content.

    This is intentionally lightweight. It is not responsible for
    medicine-name normalization; that remains the job of the local
    medicine normalizer.
    """

    text = str(value or "").strip().lower()

    # Normalize common separators such as "500-mg" -> "500 mg".
    text = re.sub(r"(?<=\d)[-_]+(?=[a-z])", " ", text)

    # Collapse repeated whitespace.
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def _extract_approximate_matches(
    payload: dict | None,
) -> list[dict]:
    """
    Extract RxNorm approximate-match candidates.

    RxNorm returns candidates ordered by lexical quality. We preserve
    rank and raw score rather than pretending the score is a percentage.
    """

    if not isinstance(payload, dict):
        return []

    approximate_group = payload.get("approximateGroup") or {}
    candidates = approximate_group.get("candidate") or []

    if isinstance(candidates, dict):
        candidates = [candidates]

    results: list[dict] = []

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue

        rxcui = str(candidate.get("rxcui") or "").strip()

        if not rxcui:
            continue

        raw_score = _safe_float(candidate.get("score"))

        try:
            rank = int(candidate.get("rank") or 999999)
        except (TypeError, ValueError):
            rank = 999999

        name = str(candidate.get("name") or "").strip()
        source = str(candidate.get("source") or "").strip()

        results.append(
            {
                "rxcui": rxcui,
                "rxaui": (
                    str(candidate.get("rxaui") or "").strip()
                    or None
                ),
                "score": raw_score,
                "rank": rank,
                "name": name or None,
                "source": source or None,
            }
        )

    return results


def _get_rxnorm_name(
    rxcui: str,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> str | None:
    """
    Retrieve the RxNorm concept name for an RxCUI.

    This is a fallback because approximate-match responses may omit
    names depending on source vocabulary restrictions.
    """

    url = (
        f"{RXNORM_BASE_URL}/rxcui/"
        f"{quote(str(rxcui), safe='')}/property.json"
        "?propName=RxNorm%20Name"
    )

    try:
        payload = _http_get_json(
            url,
            timeout=timeout,
        )

        properties = payload.get("propConceptGroup") or {}
        concepts = properties.get("propConcept") or []

        if isinstance(concepts, dict):
            concepts = [concepts]

        for concept in concepts:
            if not isinstance(concept, dict):
                continue

            value = str(
                concept.get("propValue") or ""
            ).strip()

            if value:
                return value

    except Exception:
        logger.debug(
            "Unable to retrieve RxNorm name for RxCUI %s",
            rxcui,
            exc_info=True,
        )

    return None


def _derive_external_confidence(
    *,
    rank: int,
    raw_score: float | None,
    candidate_count: int,
) -> float:
    """
    Convert RxNorm ranking information into a conservative bounded
    source-confidence signal.

    IMPORTANT:
    RxNorm's raw approximate-match score is not a percentage.
    We deliberately do not use raw_score / 100.

    The resulting value is an internal evidence signal only and is
    capped below the local auto-accept threshold.
    """

    # Rank 1 is the strongest external candidate, but we still keep
    # the result below the local acceptance threshold.
    rank_component = {
        1: 0.74,
        2: 0.66,
        3: 0.60,
        4: 0.55,
    }.get(rank, 0.50)

    # If several candidates are returned, reduce confidence slightly.
    if candidate_count > 1 and rank == 1:
        rank_component -= min(
            0.08,
            (candidate_count - 1) * 0.02,
        )

    # Use the raw score only comparatively, never as a percentage.
    score_adjustment = 0.0

    if raw_score is not None:
        if raw_score >= 20:
            score_adjustment = 0.02
        elif raw_score >= 10:
            score_adjustment = 0.01
        elif raw_score < 1:
            score_adjustment = -0.03

    confidence = rank_component + score_adjustment

    return max(
        0.0,
        min(
            MAX_EXTERNAL_SOURCE_CONFIDENCE,
            confidence,
        ),
    )


def lookup_rxnorm(
    medicine_text: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> list[dict]:
    """
    Search RxNorm for approximate medicine matches.

    Returns advisory hypotheses with provenance metadata.
    External matches are never marked clinically verified.
    """

    medicine_text = str(
        medicine_text or ""
    ).strip()

    if not medicine_text:
        return []

    if top_k <= 0:
        return []

    encoded_term = quote(
        medicine_text,
        safe="",
    )

    url = (
        f"{RXNORM_BASE_URL}/approximateTerm.json"
        f"?term={encoded_term}"
        f"&maxEntries={max(1, min(top_k, 100))}"
    )

    try:
        payload = _http_get_json(
            url,
            timeout=timeout,
        )

        candidates = _extract_approximate_matches(
            payload
        )

        if not candidates:
            return []

        candidates.sort(
            key=lambda item: (
                item["rank"],
                -item["score"],
            )
        )

        # Keep the requested number of candidates.
        candidates = candidates[:top_k]

        candidate_count = len(candidates)

        results: list[dict] = []

        for candidate in candidates:
            rxcui = candidate["rxcui"]

            normalized_name = candidate.get("name")

            if not normalized_name:
                normalized_name = _get_rxnorm_name(
                    rxcui,
                    timeout=timeout,
                )

            if not normalized_name:
                # We have an identifier but no usable concept name.
                # Do not manufacture a medicine name.
                continue

            raw_score = candidate.get("score")
            rank = candidate.get(
                "rank",
                999999,
            )

            source_confidence = _derive_external_confidence(
                rank=rank,
                raw_score=raw_score,
                candidate_count=candidate_count,
            )

            results.append(
                {
                    "normalized_name": normalized_name,
                    "generic_name": normalized_name,
                    "matched_term": medicine_text,
                    "rxcui": rxcui,
                    "rxaui": candidate.get("rxaui"),
                    "raw_rxnorm_score": raw_score,
                    "rank": rank,
                    "source": "RxNorm",
                    "source_id": rxcui,
                    "match_method": "approximate_term",
                    "source_confidence": source_confidence,
                    "clinically_verified": False,
                    "external": True,
                }
            )

        return results

    except Exception:
        # External knowledge must never break prescription analysis.
        logger.warning(
            "RxNorm lookup failed for medicine candidate: %s",
            medicine_text,
            exc_info=True,
        )
        return []


def lookup_external_medicine(
    medicine_text: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> list[dict]:
    """
    Unified external medicine lookup entry point.

    Currently backed by RxNorm. Keeping this abstraction separate
    allows future CDSCO/reference adapters to be added without
    changing the normalizer.

    Results are cached in-process (TTL 1 hour) to avoid repeated
    live API calls for the same medicine text within a worker lifetime.
    The cache is purely advisory — it never replaces the local
    curated vocabulary for previously imported medicines.
    """

    normalised = _normalize_match_text(medicine_text)
    cache_key = (normalised, top_k)

    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        result = lookup_rxnorm(
            medicine_text,
            top_k=top_k,
            timeout=timeout,
        )
    except Exception:
        logger.warning(
            "External medicine lookup failed.",
            exc_info=True,
        )
        return []

    _cache_put(cache_key, result)
    return result