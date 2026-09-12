from __future__ import annotations

from typing import Any

from backend.services.medicine_normalizer import get_ranked_medicine_hypotheses
from backend.services.medicine_evidence import rank_hypotheses_by_evidence
from backend.services.medicine_resolver import resolve_medicine_candidate


def _determine_prescription_status(medicines: list[dict[str, Any]]) -> str:
    if not medicines:
        return "no_medicines_detected"

    if any(medicine.get("needs_review") for medicine in medicines):
        return "review_required"

    return "accepted"


def interpret_medicine_candidate(
    candidate: dict[str, Any],
) -> dict[str, Any]:

    ranked_hypotheses = get_ranked_medicine_hypotheses(
        candidate
    )

    ranked_hypotheses = rank_hypotheses_by_evidence(
        candidate,
        ranked_hypotheses,
    )

    resolution = resolve_medicine_candidate(
        candidate,
        ranked_hypotheses,
    )

    top_hypothesis = resolution.get("top_hypothesis") or {}

    resolution_status = resolution.get("status")

    # A medicine can only be considered fully accepted when
    # identity AND clinically relevant strength evidence agree.
    resolution_requires_review = resolution_status != "accepted"

    resolved_name = top_hypothesis.get("normalized_name")
    resolved_generic = top_hypothesis.get("generic_name")

    original_name = candidate.get("name")

    # Preserve the prescription's explicitly extracted strength.
    # Never silently replace it with the vocabulary hypothesis strength.
    strength_value = candidate.get("strength_value")
    strength_unit = candidate.get("strength_unit")

    extraction_confidence = candidate.get(
        "extraction_confidence"
    )

    normalization_confidence = candidate.get(
        "normalization_confidence"
    )

    if normalization_confidence is None:
        normalization_confidence = candidate.get(
            "confidence"
        )

    candidate_confidence = candidate.get("confidence")

    if candidate_confidence is None:
        candidate_confidence = candidate.get(
            "extraction_confidence"
        )

    if resolution_requires_review:
        confidence = min(
            float(candidate_confidence)
            if candidate_confidence is not None
            else 0.0,
            float(resolution.get("evidence", {}).get("top_score") or 0.0),
        )
    else:
        confidence = (
            float(candidate_confidence)
            if candidate_confidence is not None
            else 0.0
        )

    result = {
        "raw_text": candidate.get("raw_text"),
        "medicine_text": resolved_name or original_name,

        "ocr_confidence": candidate.get(
            "ocr_confidence",
            extraction_confidence,
        ),

        "candidate_score": candidate.get(
            "candidate_score",
            candidate.get("normalization_confidence"),
        ),

        "name": resolved_name or original_name,
        "generic_name": resolved_generic
        or candidate.get("generic_name")
        or original_name,

        "brand_name": candidate.get(
            "brand_name"
        ),

        "strength_value": strength_value,
        "strength_unit": strength_unit,

        "strength_components": candidate.get(
            "strength_components",
            [],
        ),

        "dose_value": candidate.get(
            "dose_value"
        ),
        "dose_unit": candidate.get(
            "dose_unit"
        ),

        "route": candidate.get(
            "route"
        ),

        "frequency_value": candidate.get(
            "frequency_value"
        ),
        "frequency_unit": candidate.get(
            "frequency_unit"
        ),

        "duration_value": candidate.get(
            "duration_value"
        ),
        "duration_unit": candidate.get(
            "duration_unit"
        ),

        "instructions": candidate.get(
            "instructions"
        ),

        "daily_dose_value": candidate.get(
            "daily_dose_value"
        ),
        "daily_dose_unit": candidate.get(
            "daily_dose_unit"
        ),

        "daily_dose_components": candidate.get(
            "daily_dose_components",
            [],
        ),

        "extraction_confidence": extraction_confidence,
        "normalization_confidence": normalization_confidence,

        "confidence": round(
            max(0.0, min(1.0, confidence)),
            3,
        ),

        "needs_review": (
            bool(candidate.get("needs_review"))
            or resolution_requires_review
        ),

        "raw_strength_verified": (
            resolution.get("evidence", {}).get(
                "strength_compatible"
            )
            is True
        ),

        "strength_verification": (
            resolution.get("evidence", {}).get(
                "strength_reason"
            )
        ),

        "matched_term": candidate.get(
            "matched_term"
        ),

        "evidence": candidate.get(
            "evidence"
        ),

        "resolution": resolution,
    }

    return result


def interpret_prescription(
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:

    medicines = [
        interpret_medicine_candidate(candidate)
        for candidate in candidates
    ]

    accepted_count = sum(
        1
        for medicine in medicines
        if not medicine.get("needs_review")
    )

    review_required_count = sum(
        1
        for medicine in medicines
        if medicine.get("needs_review")
    )

    status = _determine_prescription_status(
        medicines
    )

    return {
        "status": status,
        "medicine_count": len(medicines),
        "accepted_count": accepted_count,
        "review_required_count": review_required_count,
        "medicines": medicines,
    }
