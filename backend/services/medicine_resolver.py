"""
Medicine Resolution Layer

Makes a safety-oriented decision from ranked medicine hypotheses.

This layer does NOT diagnose or prescribe.

It decides whether the available evidence is:

    - strong enough to accept a hypothesis
    - uncertain and requires human/pharmacist review
    - too weak to identify the medicine

The system should prefer uncertainty over an unsafe guess.
"""

from __future__ import annotations


# ---------------------------------------------------------
# Resolution thresholds
# ---------------------------------------------------------

# Minimum evidence score required for automatic acceptance.
AUTO_ACCEPT_THRESHOLD = 0.78

# Minimum evidence score for a meaningful hypothesis.
REVIEW_THRESHOLD = 0.45

# Minimum separation between the first and second hypotheses.
# A small margin means the candidates are too close.
MINIMUM_MARGIN = 0.10


# ---------------------------------------------------------
# Utility
# ---------------------------------------------------------

def _safe_float(value) -> float:
    """Safely convert a value to float."""

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------
# Main resolver
# ---------------------------------------------------------

def resolve_medicine_candidate(
    candidate: dict,
    ranked_hypotheses: list[dict],
) -> dict:
    """
    Resolve a medicine candidate using evidence-ranked hypotheses.

    Returns one of:

        accepted
        needs_review
        unknown

    The resolver never invents a medicine when evidence
    is insufficient.
    """

    # -----------------------------------------------------
    # No hypotheses
    # -----------------------------------------------------

    if not ranked_hypotheses:
        return {
            "status": "unknown",
            "top_hypothesis": None,
            "alternatives": [],
            "evidence": {
                "ocr_confidence": _safe_float(
                    candidate.get("ocr_confidence")
                ),
                "top_score": 0.0,
                "second_score": 0.0,
                "margin": 0.0,
            },
            "reason": "no_medicine_hypotheses",
        }

    # -----------------------------------------------------
    # Top hypothesis
    # -----------------------------------------------------

    top = ranked_hypotheses[0]

    top_score = _safe_float(
        top.get("evidence_score")
    )

    # -----------------------------------------------------
    # Second hypothesis
    # -----------------------------------------------------

    second_score = (
        _safe_float(
            ranked_hypotheses[1].get(
                "evidence_score"
            )
        )
        if len(ranked_hypotheses) > 1
        else 0.0
    )

    margin = top_score - second_score

    # -----------------------------------------------------
    # OCR confidence
    # -----------------------------------------------------

    ocr_confidence = _safe_float(
        candidate.get(
            "ocr_confidence",
            0.0,
        )
    )

    # -----------------------------------------------------
    # Common response data
    # -----------------------------------------------------

    evidence = {
        "ocr_confidence": round(
            ocr_confidence,
            3,
        ),
        "top_score": round(
            top_score,
            3,
        ),
        "second_score": round(
            second_score,
            3,
        ),
        "margin": round(
            margin,
            3,
        ),
    }

    # -----------------------------------------------------
    # Alternatives
    # -----------------------------------------------------

    alternatives = [
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
            "score": hypothesis.get(
                "evidence_score"
            ),
        }
        for hypothesis in ranked_hypotheses[1:3]
    ]

    # -----------------------------------------------------
    # Safety check 1:
    # Extremely weak evidence
    # -----------------------------------------------------

    if top_score < REVIEW_THRESHOLD:

        return {
            "status": "unknown",
            "top_hypothesis": None,
            "alternatives": alternatives,
            "evidence": evidence,
            "reason": "evidence_too_weak",
        }

    # -----------------------------------------------------
    # Safety check 2:
    # Competing hypotheses too close
    # -----------------------------------------------------

    if (
        len(ranked_hypotheses) > 1
        and margin < MINIMUM_MARGIN
    ):

        return {
            "status": "needs_review",
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
            },
            "alternatives": alternatives,
            "evidence": evidence,
            "reason": (
                "multiple_medicine_hypotheses_are_close"
            ),
        }

    # -----------------------------------------------------
    # Safety check 3:
    # Strong evidence but poor OCR
    #
    # We still require review when the underlying OCR
    # confidence is very poor.
    # -----------------------------------------------------

    if (
        top_score >= AUTO_ACCEPT_THRESHOLD
        and ocr_confidence < 0.40
    ):

        return {
            "status": "needs_review",
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
            },
            "alternatives": alternatives,
            "evidence": evidence,
            "reason": (
                "strong_hypothesis_but_low_ocr_confidence"
            ),
        }

    # -----------------------------------------------------
    # Automatic acceptance
    # -----------------------------------------------------

    if top_score >= AUTO_ACCEPT_THRESHOLD:

        return {
            "status": "accepted",
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
            },
            "alternatives": alternatives,
            "evidence": evidence,
            "reason": "sufficient_evidence",
        }

    # -----------------------------------------------------
    # Everything else requires review
    # -----------------------------------------------------

    return {
        "status": "needs_review",
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
        },
        "alternatives": alternatives,
        "evidence": evidence,
        "reason": "best_hypothesis_not_strong_enough",
    }