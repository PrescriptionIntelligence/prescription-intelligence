from __future__ import annotations

from typing import Any
import re


AUTO_ACCEPT_THRESHOLD = 0.78
REVIEW_THRESHOLD = 0.45
MINIMUM_MARGIN = 0.10


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None

        return float(value)

    except (TypeError, ValueError):
        return None


def _normalize_strength_unit(value: Any) -> str | None:
    if value is None:
        return None

    unit = str(value).strip().lower()

    aliases = {
        "milligram": "mg",
        "milligrams": "mg",
        "mg": "mg",
        "microgram": "mcg",
        "micrograms": "mcg",
        "mcg": "mcg",
        "gram": "g",
        "grams": "g",
        "g": "g",
        "milliliter": "ml",
        "milliliters": "ml",
        "ml": "ml",
        "%": "%",
    }

    return aliases.get(unit, unit)


def _extract_candidate_strength(
    candidate: dict[str, Any],
) -> tuple[float, str] | None:

    value = candidate.get("strength_value")
    unit = candidate.get("strength_unit")

    if value is None:
        strength = candidate.get("strength")

        if isinstance(strength, dict):
            value = strength.get("value")
            unit = strength.get("unit")

        elif isinstance(strength, str):
            match = re.search(
                r"(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml|%)",
                strength,
                re.IGNORECASE,
            )

            if match:
                value = match.group(1)
                unit = match.group(2)

    numeric_value = _safe_float(value)
    normalized_unit = _normalize_strength_unit(unit)

    if (
        numeric_value is None
        or normalized_unit is None
    ):
        return None

    return numeric_value, normalized_unit


def _extract_hypothesis_strength(
    hypothesis: dict[str, Any],
) -> tuple[float, str] | None:

    value = hypothesis.get("strength_value")
    unit = hypothesis.get("strength_unit")

    numeric_value = _safe_float(value)
    normalized_unit = _normalize_strength_unit(unit)

    if (
        numeric_value is None
        or normalized_unit is None
    ):
        return None

    return numeric_value, normalized_unit


def _strength_compatibility(
    candidate: dict[str, Any],
    hypothesis: dict[str, Any],
) -> tuple[bool | None, str]:
    """
    Returns:

        (True, reason)
            explicit strengths match

        (False, reason)
            explicit strengths conflict

        (None, reason)
            strength cannot be compared
    """
    candidate_strength = _extract_candidate_strength(
        candidate
    )

    hypothesis_strength = _extract_hypothesis_strength(
        hypothesis
    )

    if candidate_strength is None:
        return None, "candidate_strength_unavailable"

    if hypothesis_strength is None:
        return None, "hypothesis_strength_unavailable"

    candidate_value, candidate_unit = candidate_strength
    hypothesis_value, hypothesis_unit = hypothesis_strength

    if candidate_unit != hypothesis_unit:
        return (
            False,
            f"strength_unit_conflict:"
            f"{candidate_value:g}{candidate_unit}"
            f"_vs_"
            f"{hypothesis_value:g}{hypothesis_unit}",
        )

    if abs(candidate_value - hypothesis_value) > 1e-9:
        return (
            False,
            f"strength_conflict:"
            f"{candidate_value:g}{candidate_unit}"
            f"_vs_"
            f"{hypothesis_value:g}{hypothesis_unit}",
        )

    return True, "strength_match"


def _is_external_hypothesis(
    hypothesis: dict[str, Any],
) -> bool:
    """
    Detect hypotheses originating from external medicine
    terminology/knowledge sources.

    The normalizer may expose provenance under either
    `source` or `provenance`. We intentionally support
    both representations.
    """
    source_values = []

    for key in (
        "source",
        "provenance",
        "source_type",
        "origin",
    ):
        value = hypothesis.get(key)

        if value is not None:
            source_values.append(
                str(value).strip().lower()
            )

    for value in source_values:
        if (
            "external" in value
            or "knowledge" in value
            or "external_knowledge" in value
        ):
            return True

    return False


def _determine_resolution_status(
    top_score: float | None,
    second_score: float | None,
    ocr_confidence: float | None,
    strength_compatible: bool | None,
    external_hypothesis: bool = False,
) -> tuple[str, str]:

    if top_score is None:
        return "unknown", "missing_evidence_score"

    if strength_compatible is False:
        return "needs_review", "strength_conflict"

    if top_score < REVIEW_THRESHOLD:
        return "unknown", "insufficient_evidence"

    if second_score is not None:
        margin = top_score - second_score

        if margin < MINIMUM_MARGIN:
            return "needs_review", "ambiguous_match"

    if (
        ocr_confidence is not None
        and ocr_confidence < 0.40
    ):
        return "needs_review", "poor_ocr_confidence"

    if external_hypothesis:
        return (
            "needs_review",
            "external_hypothesis_requires_review",
        )

    if top_score >= AUTO_ACCEPT_THRESHOLD:
        return "accepted", "sufficient_evidence"

    return "needs_review", "moderate_evidence"


def resolve_medicine_candidate(
    candidate: dict[str, Any],
    ranked_hypotheses: list[dict[str, Any]],
) -> dict[str, Any]:

    if not ranked_hypotheses:
        return {
            "status": "unknown",
            "top_hypothesis": None,
            "alternatives": [],
            "evidence": {
                "ocr_confidence": _safe_float(
                    candidate.get("ocr_confidence")
                ),
                "top_score": None,
                "second_score": None,
                "margin": None,
                "strength_compatible": None,
                "strength_reason": (
                    "candidate_strength_unavailable"
                ),
            },
            "reason": "no_medicine_hypotheses",
        }

    top = ranked_hypotheses[0]

    top_score = _safe_float(
        top.get("evidence_score")
    )

    if top_score is None:
        top_score = _safe_float(
            top.get("score")
        )

    second_score = None

    if len(ranked_hypotheses) > 1:
        second = ranked_hypotheses[1]

        second_score = _safe_float(
            second.get("evidence_score")
        )

        if second_score is None:
            second_score = _safe_float(
                second.get("score")
            )

    margin = (
        top_score - second_score
        if (
            top_score is not None
            and second_score is not None
        )
        else None
    )

    ocr_confidence = _safe_float(
        candidate.get("ocr_confidence")
    )

    strength_compatible, strength_reason = (
        _strength_compatibility(
            candidate,
            top,
        )
    )

    external_hypothesis = _is_external_hypothesis(
        top
    )

    status, reason = _determine_resolution_status(
        top_score=top_score,
        second_score=second_score,
        ocr_confidence=ocr_confidence,
        strength_compatible=strength_compatible,
        external_hypothesis=external_hypothesis,
    )

    alternatives = []

    for hypothesis in ranked_hypotheses[1:3]:
        score = _safe_float(
            hypothesis.get("evidence_score")
        )

        if score is None:
            score = _safe_float(
                hypothesis.get("score")
            )

        alternatives.append(
            {
                "normalized_name": hypothesis.get(
                    "normalized_name"
                ),
                "generic_name": hypothesis.get(
                    "generic_name"
                ),
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
                "score": score,
                "external": _is_external_hypothesis(
                    hypothesis
                ),
            }
        )

    return {
        "status": status,
        "top_hypothesis": {
            "normalized_name": top.get(
                "normalized_name"
            ),
            "generic_name": top.get(
                "generic_name"
            ),
            "strength_value": top.get(
                "strength_value"
            ),
            "strength_unit": top.get(
                "strength_unit"
            ),
            "dosage_form": top.get(
                "dosage_form"
            ),
            "matched_term": top.get(
                "matched_term"
            ),
            "score": top_score,
            "external": external_hypothesis,
        },
        "alternatives": alternatives,
        "evidence": {
            "ocr_confidence": ocr_confidence,
            "top_score": top_score,
            "second_score": second_score,
            "margin": margin,
            "strength_compatible": strength_compatible,
            "strength_reason": strength_reason,
            "external_hypothesis": external_hypothesis,
        },
        "reason": reason,
    }