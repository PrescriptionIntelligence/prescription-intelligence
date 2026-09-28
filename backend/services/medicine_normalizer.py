import csv
import json
import re
import threading
from difflib import SequenceMatcher
from pathlib import Path

from backend.services.external_medicine_knowledge import (
    lookup_external_medicine,
)


# =========================================================
# Configuration
# =========================================================

FUZZY_MATCH_THRESHOLD = 0.85

# Minimum separation required between two DIFFERENT
# medicines before accepting the best match.
AMBIGUITY_MARGIN = 0.10

# Local matches below this level are considered weak enough
# to benefit from external knowledge.
#
# IMPORTANT:
# This does NOT mean that a score >= this value is unsafe.
# It simply controls when we ask the external knowledge layer
# for additional hypotheses.
EXTERNAL_LOOKUP_THRESHOLD = 0.85

# External terminology evidence is intentionally capped.
#
# RxNorm provides terminology matching evidence, not clinical
# verification. Therefore an external source alone should not
# be allowed to behave like a perfect local curated match.
MAX_EXTERNAL_HYPOTHESIS_SCORE = 0.74

# Common OCR character confusions in medicine names.
# These are applied only as candidate variants, never to the
# vocabulary itself.
OCR_CHARACTER_CONFUSIONS = {
    "0": "o",
    "1": "l",
    "5": "s",
    "8": "b",
}

# Ignore extremely short OCR fragments because they
# produce many accidental fuzzy matches.
MIN_TOKEN_LENGTH = 3


# =========================================================
# In-process vocabulary cache
#
# The vocabulary is loaded once per process and reused.
# Tests can call clear_vocabulary_cache() to reset state
# between test runs when they need a fresh load.
# =========================================================

_vocabulary_cache: list[dict] | None = None
_vocabulary_lock = threading.Lock()

# In-process lookup indexes built once from the vocabulary.
# Keyed by normalized (lower-case, whitespace-collapsed) text.
#   _exact_index   : exact normalized name → medicine dict
#                    (covers generic_name and brand_name)
#   _alias_index   : normalized alias → medicine dict
#
# These enable O(1) shortcut lookups before the O(N) fuzzy scan.
_exact_index: dict[str, dict] | None = None
_alias_index: dict[str, dict] | None = None


def clear_vocabulary_cache() -> None:
    """
    Reset the in-process vocabulary cache and lookup indexes.

    Call this in tests or after updating the vocabulary file
    on disk when running in a long-lived process.
    """
    global _vocabulary_cache, _exact_index, _alias_index  # noqa: PLW0603
    with _vocabulary_lock:
        _vocabulary_cache = None
        _exact_index = None
        _alias_index = None


def _build_indexes(medicines: list[dict]) -> None:
    """
    Build _exact_index and _alias_index from the loaded vocabulary.

    Must be called while _vocabulary_lock is held.

    If two medicines share the same normalized name or alias (a data
    error caught by validate_vocabulary.py), the first entry wins and
    a collision is silently skipped rather than raising.
    """
    global _exact_index, _alias_index  # noqa: PLW0603

    exact: dict[str, dict] = {}
    alias: dict[str, dict] = {}

    for medicine in medicines:
        generic = str(medicine.get("generic_name") or "").strip()
        brand = str(medicine.get("brand_name") or "").strip()

        gkey = _clean_text(generic)
        if gkey and gkey not in exact:
            exact[gkey] = medicine

        bkey = _clean_text(brand)
        if bkey and bkey != gkey and bkey not in exact:
            exact[bkey] = medicine

        for a in medicine.get("aliases") or []:
            akey = _clean_text(str(a))
            if akey and akey not in alias:
                alias[akey] = medicine

    _exact_index = exact
    _alias_index = alias


def lookup_exact(text: str) -> dict | None:
    """
    O(1) exact-name lookup using the in-process index.

    Checks generic_name and brand_name first, then aliases.

    Returns the matching medicine dict, or None.

    This function is intentionally outside the lock because:
      - it only reads from already-built index dicts
      - Python dict reads are thread-safe for built-in types
      - the calling code always loads the vocabulary first (which builds
        the indexes under the lock) before calling this function
    """
    global _exact_index, _alias_index  # noqa: PLW0603

    if _exact_index is None:
        return None

    key = _clean_text(text)
    if not key:
        return None

    hit = _exact_index.get(key)
    if hit is not None:
        return hit

    if _alias_index is not None:
        hit = _alias_index.get(key)

    return hit


# =========================================================
# Medicine vocabulary
# =========================================================

def load_medicine_vocabulary() -> list[dict]:
    """
    Load the medicine vocabulary and return a normalised list of dicts.

    Loading order (merged, deduplicated by generic_name):

    1. data/medicines/medicine_knowledge.jsonl  — rich structured format
       generated by scripts/medicines/build_seed_vocabulary.py or
       scripts/medicines/import_rxnorm.py.

    2. data/medicines/medicine_vocabulary.csv   — legacy CSV format,
       kept for backward compatibility.  CSV entries that share a
       generic_name with a JSONL record are skipped (JSONL wins).

    The result is cached in-process so repeated calls within the same
    worker process do not re-read the files.  Call
    clear_vocabulary_cache() to invalidate the cache when needed.

    Common internal format (used by the rest of this module):

        brand_name      str
        generic_name    str
        strength_value  str | None
        strength_unit   str | None
        dosage_form     str | None
        aliases         list[str]
        rxcui           str | None   (new — None for legacy CSV entries)
        active_ingredients  list[str]  (new — defaults to [generic_name])
        route           str | None   (new)
        source          str          ("rxnorm" | "csv" | ...)
    """

    global _vocabulary_cache  # noqa: PLW0603

    with _vocabulary_lock:
        if _vocabulary_cache is not None:
            return _vocabulary_cache

        medicines = _load_vocabulary_unlocked()
        _vocabulary_cache = medicines
        # Build O(1) lookup indexes now that the vocabulary is loaded.
        # _clean_text is defined later in this module but is already
        # available at call time (Python resolves names at call, not def).
        _build_indexes(medicines)
        return medicines


def _load_vocabulary_unlocked() -> list[dict]:
    """
    Internal: load and merge vocabulary files.
    Must be called while _vocabulary_lock is held.
    """

    project_root = Path(__file__).resolve().parents[2]
    data_dir = project_root / "data" / "medicines"

    jsonl_path = data_dir / "medicine_knowledge.jsonl"
    csv_path = data_dir / "medicine_vocabulary.csv"

    medicines: list[dict] = []

    # Tracks generic names already loaded (normalised lower-case)
    # to deduplicate CSV entries that overlap with JSONL.
    seen_generic: set[str] = set()

    # ----------------------------------------------------------
    # 1. Load JSONL (richer structured data)
    # ----------------------------------------------------------

    if jsonl_path.exists():
        with jsonl_path.open("r", encoding="utf-8") as fh:
            for raw_line in fh:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    record = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue

                if not isinstance(record, dict):
                    continue

                generic = str(
                    record.get("generic_name") or ""
                ).strip()

                if not generic:
                    continue

                # Build a normalised alias list that includes the
                # generic_name itself, brand_name, active_ingredients,
                # and any explicitly listed aliases.
                alias_set: set[str] = set()

                for alias in record.get("aliases") or []:
                    alias = str(alias).strip()
                    if alias:
                        alias_set.add(alias)

                brand = str(
                    record.get("brand_name") or ""
                ).strip() or None

                if brand:
                    alias_set.add(brand.lower())

                # Only add individual active ingredients as aliases
                # when the medicine has a single active ingredient.
                # Combination drugs (multiple ingredients) must NOT have
                # their individual components added as aliases, because
                # that would make "Amoxicillin + Clavulanate" score a
                # perfect match for a query for "Amoxicillin" alone,
                # causing false ambiguity in the resolver.
                active_ingredients = [
                    str(i).strip()
                    for i in (record.get("active_ingredients") or [])
                    if str(i).strip()
                ]
                if len(active_ingredients) == 1:
                    ingredient = active_ingredients[0]
                    if ingredient.lower() != generic.lower():
                        alias_set.add(ingredient.lower())

                medicine = {
                    "brand_name": brand or generic,
                    "generic_name": generic,
                    "strength_value": (
                        str(record.get("strength_value") or "").strip()
                        or None
                    ),
                    "strength_unit": (
                        str(record.get("strength_unit") or "").strip()
                        or None
                    ),
                    "dosage_form": (
                        str(record.get("dosage_form") or "").strip()
                        or None
                    ),
                    "aliases": sorted(alias_set),
                    "rxcui": (
                        str(record.get("rxcui") or "").strip() or None
                    ),
                    "active_ingredients": (
                        list(record.get("active_ingredients") or [generic])
                    ),
                    "route": (
                        str(record.get("route") or "").strip() or None
                    ),
                    "source": str(
                        record.get("source") or "rxnorm"
                    ),
                }

                medicines.append(medicine)
                seen_generic.add(generic.lower())
                # Also track brand_name and all aliases so that CSV entries
                # whose generic_name/brand_name is an alias for a JSONL entry
                # are correctly skipped.
                #
                # Examples:
                #   "Paracetamol" CSV entry → alias of JSONL "Acetaminophen"
                #   "Sizodon Plus" CSV brand → JSONL generic_name "Sizodon Plus"
                if brand:
                    seen_generic.add(brand.lower())
                for alias in medicine.get("aliases") or []:
                    seen_generic.add(str(alias).lower())

    # ----------------------------------------------------------
    # 2. Load legacy CSV (backward-compatible)
    # ----------------------------------------------------------

    if csv_path.exists():

        with csv_path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as file:

            reader = csv.DictReader(file)

            required_columns = {
                "brand_name",
                "generic_name",
                "strength_value",
                "strength_unit",
                "dosage_form",
                "aliases",
            }

            if not reader.fieldnames:
                raise ValueError(
                    "Medicine CSV has no header row."
                )

            missing_columns = (
                required_columns
                - set(reader.fieldnames)
            )

            if missing_columns:
                raise ValueError(
                    "Medicine CSV is missing columns: "
                    + ", ".join(sorted(missing_columns))
                )

            for row in reader:

                generic = row.get("generic_name", "").strip()
                csv_brand = row.get("brand_name", "").strip()

                # Skip CSV entries already covered by JSONL.
                # Check both generic_name and brand_name against
                # seen_generic so that combination drugs whose JSONL
                # entry uses the brand name as the canonical identifier
                # (e.g. "Sizodon Plus") correctly suppress the CSV row
                # whose generic_name is "Risperidone + Trihexyphenidyl".
                if generic.lower() in seen_generic:
                    continue
                if csv_brand and csv_brand.lower() in seen_generic:
                    continue

                aliases = row.get("aliases", "")
                aliases = [
                    alias.strip().lower()
                    for alias in aliases.split("|")
                    if alias.strip()
                ]

                medicine = {
                    "brand_name": row.get(
                        "brand_name", ""
                    ).strip(),
                    "generic_name": generic,
                    "strength_value": row.get(
                        "strength_value", ""
                    ).strip() or None,
                    "strength_unit": row.get(
                        "strength_unit", ""
                    ).strip() or None,
                    "dosage_form": row.get(
                        "dosage_form", ""
                    ).strip() or None,
                    "aliases": aliases,
                    "rxcui": None,
                    "active_ingredients": [generic] if generic else [],
                    "route": None,
                    "source": "csv",
                }

                if not any(
                    medicine[k]
                    for k in (
                        "brand_name",
                        "generic_name",
                        "strength_value",
                        "dosage_form",
                    )
                ):
                    continue

                medicines.append(medicine)
                seen_generic.add(generic.lower())

    if not medicines:
        raise FileNotFoundError(
            f"No medicine vocabulary found in {data_dir}. "
            "Expected medicine_knowledge.jsonl or medicine_vocabulary.csv."
        )

    return medicines


# =========================================================
# Text cleaning
# =========================================================

def _clean_text(text: str) -> str:
    """
    Normalize OCR text before comparison.
    """

    if not text:
        return ""

    text = text.lower()

    # Replace punctuation/symbols with spaces.
    text = re.sub(
        r"[^a-z0-9\s]",
        " ",
        text,
    )

    # Normalize whitespace.
    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def _tokenize(text: str) -> list[str]:
    """
    Split cleaned text into meaningful tokens.

    Very short fragments are ignored because OCR noise
    such as single letters can create false matches.
    """

    clean = _clean_text(text)

    return [
        token
        for token in clean.split()
        if len(token) >= MIN_TOKEN_LENGTH
    ]


# =========================================================
# OCR candidate variants
# =========================================================

def _generate_ocr_variants(
    text: str,
) -> list[dict]:
    """
    Generate conservative OCR-corrected variants.

    The original candidate is always retained.

    Each variant records whether it was produced by OCR
    correction so that corrected text is NEVER reported as
    an exact match to the original OCR input.
    """

    if not text:
        return []

    variants = [
        {
            "text": text,
            "ocr_corrected": False,
        }
    ]

    for source_char, replacement_char in (
        OCR_CHARACTER_CONFUSIONS.items()
    ):

        if source_char not in text:
            continue

        variant = text.replace(
            source_char,
            replacement_char,
        )

        if not variant or variant == text:
            continue

        if any(
            item["text"] == variant
            for item in variants
        ):
            continue

        variants.append(
            {
                "text": variant,
                "ocr_corrected": True,
            }
        )

    return variants


# =========================================================
# Similarity
# =========================================================

def _similarity(
    a: str,
    b: str,
) -> float:
    """
    Calculate SequenceMatcher similarity.
    """

    if not a or not b:
        return 0.0

    return SequenceMatcher(
        None,
        a,
        b,
    ).ratio()


# =========================================================
# Medicine search terms
# =========================================================

def _get_match_terms(
    medicine: dict,
) -> list[str]:
    """
    Return all searchable names belonging to one medicine.

    Brand name, generic name and aliases are treated as
    evidence for the SAME medicine.
    """

    terms = []

    for key in (
        "brand_name",
        "generic_name",
    ):

        value = medicine.get(key)

        if value:
            terms.append(value)

    aliases = medicine.get(
        "aliases",
        [],
    )

    terms.extend(
        alias
        for alias in aliases
        if alias
    )

    return terms


# =========================================================
# Candidate preparation
# =========================================================

def _prepare_candidate(
    clean_text: str,
) -> str:
    """
    Remove common prescription artifacts.

    Medicine identification is still performed only against
    the remaining text.
    """

    candidate = re.sub(
        r"\b(tab|tablet|cap|capsule|syr|syrup|inj|injection)\b",
        " ",
        clean_text,
        flags=re.IGNORECASE,
    )

    # Remove standalone numeric artifacts.
    candidate = re.sub(
        r"\b\d+\b",
        " ",
        candidate,
    )

    candidate = re.sub(
        r"\s+",
        " ",
        candidate,
    ).strip()

    return candidate


# =========================================================
# Token evidence
# =========================================================

def _token_similarity_score(
    candidate_tokens: list[str],
    medicine_term: str,
) -> dict:
    """
    Compare OCR tokens individually against one medicine term.

    Returns the strongest token evidence.
    """

    clean_term = _clean_text(
        medicine_term
    )

    if not clean_term:
        return {
            "score": 0.0,
            "matched_token": None,
            "exact_match": False,
            "prefix_match": False,
        }

    best_score = 0.0
    matched_token = None
    exact_match = False
    prefix_match = False

    for token in candidate_tokens:

        similarity = _similarity(
            token,
            clean_term,
        )

        if token == clean_term:

            similarity = 1.0

        elif (
            len(token) >= 4
            and (
                clean_term.startswith(token)
                or token.startswith(clean_term)
            )
        ):

            similarity = max(
                similarity,
                0.90,
            )

        if similarity > best_score:

            best_score = similarity
            matched_token = token
            exact_match = (
                token == clean_term
            )
            prefix_match = (
                len(token) >= 4
                and (
                    clean_term.startswith(token)
                    or token.startswith(clean_term)
                )
            )

    return {
        "score": best_score,
        "matched_token": matched_token,
        "exact_match": exact_match,
        "prefix_match": prefix_match,
    }


# =========================================================
# Score one medicine
# =========================================================

def _score_medicine(
    candidate: str,
    medicine: dict,
) -> dict | None:
    """
    Calculate medicine-level evidence.

    IMPORTANT:

    All aliases belonging to one medicine are combined into
    a single medicine-level result.

    This prevents aliases of the same medicine from creating
    artificial ambiguity.
    """

    terms = _get_match_terms(
        medicine
    )

    if not terms:
        return None

    candidate_tokens = _tokenize(
        candidate
    )

    if not candidate_tokens:
        return None

    best_result = None

    for term in terms:

        clean_term = _clean_text(
            term
        )

        if not clean_term:
            continue

        # ---------------------------------------------
        # Full candidate similarity
        # ---------------------------------------------

        full_score = _similarity(
            candidate,
            clean_term,
        )

        # ---------------------------------------------
        # Token evidence
        # ---------------------------------------------

        token_result = _token_similarity_score(
            candidate_tokens,
            clean_term,
        )

        token_score = token_result[
            "score"
        ]

        # ---------------------------------------------
        # Multi-token evidence
        # ---------------------------------------------

        term_tokens = _tokenize(
            clean_term
        )

        matched_term_tokens = 0

        for term_token in term_tokens:

            best_token_similarity = max(
                (
                    _similarity(
                        candidate_token,
                        term_token,
                    )
                    for candidate_token in candidate_tokens
                ),
                default=0.0,
            )

            if best_token_similarity >= 0.80:
                matched_term_tokens += 1

        if term_tokens:

            token_coverage = (
                matched_term_tokens
                / len(term_tokens)
            )

        else:

            token_coverage = 0.0

        # ---------------------------------------------
        # Evidence combination
        # ---------------------------------------------

        if token_result["exact_match"]:

            score = 1.0

        elif (
            len(term_tokens) > 1
            and token_coverage >= 0.5
        ):

            # Multi-word medicine names receive support
            # when multiple components agree.
            score = max(
                token_score,
                token_coverage * 0.95,
                full_score,
            )

        elif token_result["prefix_match"]:

            score = max(
                token_score,
                0.90,
            )

        else:

            # Full-text similarity is intentionally weighted
            # conservatively because OCR lines can contain
            # large amounts of unrelated noise.
            score = max(
                token_score,
                full_score * 0.75,
            )

        result = {
            "medicine": medicine,
            "matched_term": term,
            "score": score,
            "full_score": full_score,
            "token_score": token_score,
            "token_coverage": token_coverage,
            "matched_token": token_result[
                "matched_token"
            ],
            "exact_match": token_result[
                "exact_match"
            ],
            "prefix_match": token_result[
                "prefix_match"
            ],
        }

        if (
            best_result is None
            or result["score"]
            > best_result["score"]
        ):

            best_result = result

    return best_result


# =========================================================
# Find best local fuzzy match
# =========================================================

def _find_best_fuzzy_match(
    clean_text: str,
    medicines: list[dict],
):
    """
    Find the best medicine vocabulary match.

    OCR-corrected candidate variants are evaluated in addition
    to the original candidate.

    IMPORTANT:

    OCR correction may improve the matching score, but it must
    NEVER make the original OCR text appear to be an exact
    match.

    Ambiguity is checked between DIFFERENT medicines,
    not between aliases of the same medicine.
    """

    if not clean_text:
        return None

    candidate = _prepare_candidate(
        clean_text
    )

    if not candidate:
        return None

    candidate_variants = _generate_ocr_variants(
        candidate
    )

    results = []

    # -----------------------------------------------------
    # Score each medicine against every OCR variant.
    # -----------------------------------------------------

    for medicine in medicines:

        best_medicine_result = None

        for variant_info in candidate_variants:

            candidate_variant = variant_info["text"]
            ocr_corrected = variant_info[
                "ocr_corrected"
            ]

            result = _score_medicine(
                candidate_variant,
                medicine,
            )

            if result is None:
                continue

            result["candidate_variant"] = (
                candidate_variant
            )

            result["ocr_corrected"] = (
                ocr_corrected
            )

            # -------------------------------------------------
            # Evidence must be calculated against the ORIGINAL
            # OCR candidate, not the corrected variant.
            # -------------------------------------------------

            original_result = _score_medicine(
                candidate,
                medicine,
            )

            if original_result is not None:

                result["original_full_score"] = (
                    original_result["full_score"]
                )

                result["original_token_score"] = (
                    original_result["token_score"]
                )

                result["original_matched_token"] = (
                    original_result["matched_token"]
                )

                result["original_exact_match"] = (
                    original_result["exact_match"]
                )

                result["original_prefix_match"] = (
                    original_result["prefix_match"]
                )

            else:

                result["original_full_score"] = 0.0
                result["original_token_score"] = 0.0
                result["original_matched_token"] = None
                result["original_exact_match"] = False
                result["original_prefix_match"] = False

            if (
                best_medicine_result is None
                or result["score"]
                > best_medicine_result["score"]
            ):

                best_medicine_result = result

        if best_medicine_result is not None:
            results.append(
                best_medicine_result
            )

    if not results:
        return None

    # -----------------------------------------------------
    # Highest medicine-level score first.
    # -----------------------------------------------------

    results.sort(
        key=lambda x: x["score"],
        reverse=True,
    )

    best = results[0]

    second_score = (
        results[1]["score"]
        if len(results) > 1
        else 0.0
    )

    # -----------------------------------------------------
    # Store ambiguity evidence.
    # -----------------------------------------------------

    best["second_best_score"] = second_score

    best["ranked_results"] = [
        {
            "brand_name": result[
                "medicine"
            ].get("brand_name"),

            "matched_term": result.get(
                "matched_term"
            ),

            "score": round(
                result["score"],
                3,
            ),
        }
        for result in results[:5]
    ]

    # -----------------------------------------------------
    # Safety check 1:
    # Match must be strong enough.
    # -----------------------------------------------------

    if best["score"] < FUZZY_MATCH_THRESHOLD:
        return None

    # -----------------------------------------------------
    # Safety check 2:
    # Best and second-best DIFFERENT medicines
    # must be sufficiently separated.
    #
    # Exception: a perfect score (exact match) is never
    # ambiguous regardless of how close the runner-up is.
    # -----------------------------------------------------

    if (
        best["score"] < 1.0
        and len(results) > 1
        and (
            best["score"] - second_score
            < AMBIGUITY_MARGIN
        )
    ):
        return None

    return best


# =========================================================
# Estimate best local score
# =========================================================

def _estimate_best_score(
    clean_text: str,
    medicines: list[dict],
) -> float:
    """
    Estimate the strongest medicine-level similarity.

    OCR-corrected candidate variants are considered.

    Used only when no reliable local match was accepted.
    """

    candidate = _prepare_candidate(
        clean_text
    )

    if not candidate:
        return 0.0

    candidate_variants = _generate_ocr_variants(
        candidate
    )

    best_score = 0.0

    for medicine in medicines:

        for variant_info in candidate_variants:

            candidate_variant = variant_info["text"]

            result = _score_medicine(
                candidate_variant,
                medicine,
            )

            if result is not None:

                best_score = max(
                    best_score,
                    result["score"],
                )

    return best_score


# =========================================================
# Normalize one local candidate
# =========================================================

def normalize_medicine_candidate(
    candidate: dict,
    medicines: list[dict],
) -> dict:
    """
    Normalize one medicine candidate using the LOCAL
    curated medicine vocabulary.

    This function intentionally remains local-only.

    External knowledge is integrated into the hypothesis
    layer below, where external results can be compared
    alongside local evidence without changing the behavior
    of existing direct normalization callers.
    """

    raw_text = candidate.get(
        "medicine_text",
        candidate.get(
            "text",
            "",
        ),
    )

    clean_text = _clean_text(
        raw_text
    )

    # ------------------------------------------------------------------
    # Fast path: O(1) exact index lookup before O(N) fuzzy scan.
    #
    # The prepared candidate strips dosage-form words and standalone
    # numbers (e.g. "Amoxicillin 500 mg" → "amoxicillin").  We try both
    # the original clean_text AND the prepared form so that:
    #   "Amoxicillin"       → exact generic hit
    #   "Coumadin"          → exact alias/brand hit → Warfarin
    #   "Amoxicillin 500"   → prepared "amoxicillin" → exact hit
    # ------------------------------------------------------------------
    prepared_for_index = _prepare_candidate(clean_text)

    exact_hit = lookup_exact(clean_text) or (
        lookup_exact(prepared_for_index) if prepared_for_index != clean_text else None
    )

    if exact_hit is not None:
        # Build a synthetic match structure so the return value is
        # identical in shape to a fuzzy-match result.
        return {
            "raw_text": raw_text,
            "clean_text": clean_text,
            "normalized_name": exact_hit.get("brand_name"),
            "generic_name": exact_hit.get("generic_name"),
            "strength_value": exact_hit.get("strength_value"),
            "strength_unit": exact_hit.get("strength_unit"),
            "dosage_form": exact_hit.get("dosage_form"),
            "matched_term": raw_text,
            "normalization_confidence": 1.0,
            "needs_review": False,
            "matched_token": clean_text,
            "evidence": {
                "accepted": True,
                "full_text_similarity": 1.0,
                "token_similarity": 1.0,
                "token_coverage": 1.0,
                "exact_match": True,
                "prefix_match": False,
                "ocr_corrected": False,
                "candidate_variant": clean_text,
                "second_best_score": 0.0,
                "ranked_results": [],
            },
        }

    match = _find_best_fuzzy_match(
        clean_text,
        medicines,
    )

    # -----------------------------------------------------
    # No reliable local match
    # -----------------------------------------------------

    if match is None:

        best_score = _estimate_best_score(
            clean_text,
            medicines,
        )

        return {
            "raw_text": raw_text,

            "clean_text": clean_text,

            "normalized_name": None,

            "generic_name": None,

            "strength_value": None,

            "strength_unit": None,

            "dosage_form": None,

            "matched_term": None,

            "normalization_confidence": round(
                best_score,
                3,
            ),

            "needs_review": True,

            "matched_token": None,

            "evidence": {
                "accepted": False,
                "reason": (
                    "insufficient_or_ambiguous_match"
                ),
            },
        }

    # -----------------------------------------------------
    # Reliable local match
    # -----------------------------------------------------

    medicine = match[
        "medicine"
    ]

    return {
        "raw_text": raw_text,

        "clean_text": clean_text,

        "normalized_name": medicine.get(
            "brand_name"
        ),

        "generic_name": medicine.get(
            "generic_name"
        ),

        "strength_value": medicine.get(
            "strength_value"
        ),

        "strength_unit": medicine.get(
            "strength_unit"
        ),

        "dosage_form": medicine.get(
            "dosage_form"
        ),

        "matched_term": match[
            "matched_term"
        ],

        "normalization_confidence": round(
            match["score"],
            3,
        ),

        "needs_review": False,

        "matched_token": match[
            "matched_token"
        ],

        "evidence": {
            "accepted": True,

            # Evidence from the ORIGINAL OCR text.
            "full_text_similarity": round(
                match.get(
                    "original_full_score",
                    match["full_score"],
                ),
                3,
            ),

            "token_similarity": round(
                match.get(
                    "original_token_score",
                    match["token_score"],
                ),
                3,
            ),

            "token_coverage": round(
                match["token_coverage"],
                3,
            ),

            # These describe the ORIGINAL OCR text.
            "exact_match": match.get(
                "original_exact_match",
                match["exact_match"],
            ),

            "prefix_match": match.get(
                "original_prefix_match",
                match["prefix_match"],
            ),

            "ocr_corrected": match.get(
                "ocr_corrected",
                False,
            ),

            "candidate_variant": match.get(
                "candidate_variant",
            ),

            "second_best_score": round(
                match.get(
                    "second_best_score",
                    0.0,
                ),
                3,
            ),

            "ranked_results": match.get(
                "ranked_results",
                [],
            ),
        },
    }


# =========================================================
# Normalize all local candidates
# =========================================================

def normalize_medicine_candidates(
    candidates: list[dict],
) -> list[dict]:
    """
    Normalize all detected medicine candidates using
    the local curated medicine vocabulary.
    """

    medicines = load_medicine_vocabulary()

    return [
        normalize_medicine_candidate(
            candidate,
            medicines,
        )
        for candidate in candidates
    ]


# =========================================================
# External hypothesis conversion
# =========================================================

def _convert_external_hypothesis(
    hypothesis: dict,
) -> dict | None:
    """
    Convert an external knowledge result into the internal
    hypothesis format expected by the evidence-fusion layer.

    External terminology evidence is deliberately capped.

    This prevents a high lexical score from an external
    terminology service from being interpreted as equivalent
    to a trusted local medicine match.
    """

    normalized_name = hypothesis.get(
        "normalized_name"
    )

    if not normalized_name:
        return None

    source_confidence = hypothesis.get(
        "source_confidence",
        0.0,
    )

    try:
        source_confidence = float(
            source_confidence
        )
    except (
        TypeError,
        ValueError,
    ):
        source_confidence = 0.0

    source_confidence = max(
        0.0,
        min(
            source_confidence,
            1.0,
        ),
    )

    # External evidence can contribute to ranking but
    # cannot independently behave like a perfect match.
    hypothesis_score = min(
        source_confidence,
        MAX_EXTERNAL_HYPOTHESIS_SCORE,
    )

    return {
        "normalized_name": normalized_name,

        "generic_name": hypothesis.get(
            "generic_name"
        ),

        # External sources may not provide strength/form
        # information for this particular lookup.
        "strength_value": hypothesis.get(
            "strength_value"
        ),

        "strength_unit": hypothesis.get(
            "strength_unit"
        ),

        "dosage_form": hypothesis.get(
            "dosage_form"
        ),

        "matched_term": hypothesis.get(
            "matched_term"
        ),

        "score": round(
            hypothesis_score,
            3,
        ),

        "token_score": round(
            hypothesis_score,
            3,
        ),

        "full_score": round(
            hypothesis_score,
            3,
        ),

        # -------------------------------------------------
        # Provenance
        # -------------------------------------------------

        "source": hypothesis.get(
            "source",
            "external",
        ),

        "source_id": hypothesis.get(
            "source_id"
        ),

        "match_method": hypothesis.get(
            "match_method"
        ),

        "source_confidence": round(
            source_confidence,
            3,
        ),

        "clinically_verified": bool(
            hypothesis.get(
                "clinically_verified",
                False,
            )
        ),

        "external": True,
    }


# =========================================================
# Ranked medicine hypotheses
# =========================================================

def get_ranked_medicine_hypotheses(
    candidate: dict,
    medicines: list[dict] | None = None,
    top_k: int = 3,
) -> list[dict]:
    """
    Return the most likely medicine hypotheses for a noisy
    OCR candidate.

    Resolution strategy:

        1. Search the local curated vocabulary.
        2. If local evidence is strong, return local
           hypotheses only.
        3. If local evidence is weak or absent, query the
           external medicine knowledge layer.
        4. Preserve both local and external hypotheses.
        5. Mark external results with provenance.
        6. Never treat external terminology as clinical
           verification.

    These are hypotheses, not confirmed medicines.
    """

    # Track whether the caller supplied a custom medicine list.
    # The O(1) exact-index is only valid for the full loaded vocabulary.
    # When a custom list is supplied we must fall through to the O(N) scan
    # so that tests or callers with restricted lists get correct results.
    _use_full_vocabulary = medicines is None

    if medicines is None:
        medicines = load_medicine_vocabulary()

    if top_k <= 0:
        return []

    raw_text = candidate.get(
        "medicine_text",
        candidate.get(
            "text",
            "",
        ),
    )

    clean_text = _clean_text(
        raw_text
    )

    prepared_candidate = _prepare_candidate(
        clean_text
    )

    if not prepared_candidate:
        return []

    # ------------------------------------------------------------------
    # Fast path: if the clean or prepared text is an exact vocabulary
    # hit, return a single high-confidence local hypothesis immediately
    # without the O(N) fuzzy scan.
    #
    # Only applicable when using the full loaded vocabulary, because the
    # exact index is built from that vocabulary.  Custom medicine lists
    # (e.g. single-record test fixtures) bypass this fast path.
    # ------------------------------------------------------------------
    if _use_full_vocabulary:
        exact_hit = lookup_exact(clean_text) or (
            lookup_exact(prepared_candidate)
            if prepared_candidate != clean_text
            else None
        )

        if exact_hit is not None:
            return [{
                "normalized_name": exact_hit.get("brand_name"),
                "generic_name": exact_hit.get("generic_name"),
                "strength_value": exact_hit.get("strength_value"),
                "strength_unit": exact_hit.get("strength_unit"),
                "dosage_form": exact_hit.get("dosage_form"),
                "matched_term": raw_text,
                "score": 1.0,
                "token_score": 1.0,
                "full_score": 1.0,
                "source": "curated",
                "source_id": None,
                "match_method": "exact_index",
                "source_confidence": 1.0,
                "clinically_verified": False,
                "external": False,
            }]

    # -----------------------------------------------------
    # Local hypotheses (full O(N) fuzzy scan)
    # -----------------------------------------------------

    local_results = []

    candidate_variants = _generate_ocr_variants(
        prepared_candidate
    )

    for medicine in medicines:

        best_result = None

        for variant_info in candidate_variants:

            result = _score_medicine(
                variant_info["text"],
                medicine,
            )

            if result is None:
                continue

            if (
                best_result is None
                or result["score"]
                > best_result["score"]
            ):
                best_result = result

        if best_result is None:
            continue

        result = best_result

        local_results.append(
            {
                "normalized_name": medicine.get(
                    "brand_name"
                ),

                "generic_name": medicine.get(
                    "generic_name"
                ),

                "strength_value": medicine.get(
                    "strength_value"
                ),

                "strength_unit": medicine.get(
                    "strength_unit"
                ),

                "dosage_form": medicine.get(
                    "dosage_form"
                ),

                "matched_term": result.get(
                    "matched_term"
                ),

                "score": round(
                    result.get(
                        "score",
                        0.0,
                    ),
                    3,
                ),

                "token_score": round(
                    result.get(
                        "token_score",
                        0.0,
                    ),
                    3,
                ),

                "full_score": round(
                    result.get(
                        "full_score",
                        0.0,
                    ),
                    3,
                ),

                # Local curated source.
                "source": "curated",

                "source_id": None,

                "match_method": "local_fuzzy",

                "source_confidence": round(
                    result.get(
                        "score",
                        0.0,
                    ),
                    3,
                ),

                "clinically_verified": False,

                "external": False,
            }
        )

    local_results.sort(
        key=lambda result: result["score"],
        reverse=True,
    )

    best_local_score = (
        local_results[0]["score"]
        if local_results
        else 0.0
    )

    # -----------------------------------------------------
    # Strong local match
    # -----------------------------------------------------

    if best_local_score >= EXTERNAL_LOOKUP_THRESHOLD:

        return local_results[:top_k]

    # -----------------------------------------------------
    # Weak/no local match:
    # query external knowledge.
    # -----------------------------------------------------

    external_results = []

    try:
        external_hypotheses = (
            lookup_external_medicine(
                prepared_candidate,
                top_k=top_k,
            )
        )

        for hypothesis in external_hypotheses:

            converted = (
                _convert_external_hypothesis(
                    hypothesis
                )
            )

            if converted is not None:
                external_results.append(
                    converted
                )

    except Exception:
        # The external layer is supplementary.
        #
        # If anything unexpected happens, preserve the
        # existing local-only behavior.
        external_results = []

    # -----------------------------------------------------
    # Combine local + external hypotheses.
    # -----------------------------------------------------

    combined_results = [
        *local_results,
        *external_results,
    ]

    if not combined_results:
        return []

    # -----------------------------------------------------
    # Deduplicate hypotheses representing the same generic
    # medicine from multiple sources.
    #
    # Local curated evidence is preferred when both sources
    # identify the same normalized medicine.
    # -----------------------------------------------------

    deduplicated = {}

    for result in combined_results:

        normalized_name = _clean_text(
            result.get(
                "normalized_name",
                "",
            )
        )

        generic_name = _clean_text(
            result.get(
                "generic_name",
                "",
            )
        )

        identity_key = (
            generic_name
            or normalized_name
        )

        if not identity_key:
            continue

        existing = deduplicated.get(
            identity_key
        )

        if existing is None:

            deduplicated[
                identity_key
            ] = result

            continue

        # Prefer local curated evidence over an external
        # hypothesis for the same medicine.
        if (
            existing.get("external", False)
            and not result.get(
                "external",
                False,
            )
        ):
            deduplicated[
                identity_key
            ] = result

        elif (
            existing.get("external", False)
            == result.get(
                "external",
                False,
            )
            and result.get(
                "score",
                0.0,
            )
            > existing.get(
                "score",
                0.0,
            )
        ):
            deduplicated[
                identity_key
            ] = result

    combined_results = list(
        deduplicated.values()
    )

    # -----------------------------------------------------
    # Rank combined hypotheses.
    # -----------------------------------------------------

    combined_results.sort(
        key=lambda result: result.get(
            "score",
            0.0,
        ),
        reverse=True,
    )

    return combined_results[:top_k]