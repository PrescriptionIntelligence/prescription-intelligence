"""
Prescription Interpreter

Combines medicine candidates and their resolved hypotheses
into a prescription-level intelligence result.

This layer does NOT diagnose, prescribe, or invent medicines.

Its job is to:
    - process all detected medicine candidates
    - resolve each candidate safely
    - summarize confidence
    - identify medicines requiring pharmacist review
    - preserve structured prescription instructions
    - preserve alternative hypotheses
"""

from __future__ import annotations

from backend.services.medicine_normalizer import (
    get_ranked_medicine_hypotheses,
)

from backend.services.medicine_evidence import (
    rank_hypotheses_by_evidence,
)

from backend.services.medicine_resolver import (
    resolve_medicine_candidate,
)


# ---------------------------------------------------------
# Prescription status
# ---------------------------------------------------------

def _determine_prescription_status(
    results: list[dict],
) -> str:
    """
    Determine the overall medicine-resolution status
    of a prescription.

    Possible statuses:

        accepted
        partially_resolved
        review_required
        no_medicines_detected

    Important:
        "accepted" refers only to medicine identity
        resolution.

        It does NOT mean that the prescription is clinically
        safe, appropriate, or free from drug interactions.
    """

    if not results:
        return "no_medicines_detected"

    review_count = sum(
        1
        for result in results
        if result["resolution"]["status"] == "needs_review"
    )

    accepted_count = sum(
        1
        for result in results
        if result["resolution"]["status"] == "accepted"
    )

    unknown_count = sum(
        1
        for result in results
        if result["resolution"]["status"] == "unknown"
    )

    # Every detected medicine requires review.
    if review_count + unknown_count == len(results):
        return "review_required"

    # At least one medicine is accepted, but one or more
    # medicines still require review or could not be identified.
    if review_count > 0 or unknown_count > 0:
        return "partially_resolved"

    # Every detected medicine was confidently accepted.
    if accepted_count == len(results):
        return "accepted"

    # Defensive fallback.
    return "review_required"


# ---------------------------------------------------------
# Process one medicine candidate
# ---------------------------------------------------------

def interpret_medicine_candidate(
    candidate: dict,
) -> dict:
    """
    Process one detected medicine candidate.

    Pipeline:

        candidate
            ↓
        medicine hypotheses
            ↓
        evidence fusion
            ↓
        safe resolution

    Important:
        Structured prescription fields extracted by the
        parser are intentionally preserved here so that
        downstream plan and safety layers do not lose them.
    """

    hypotheses = get_ranked_medicine_hypotheses(
        candidate
    )

    evidence_ranked = rank_hypotheses_by_evidence(
        candidate,
        hypotheses,
    )

    resolution = resolve_medicine_candidate(
        candidate,
        evidence_ranked,
    )

    return {
        # -------------------------------------------------
        # Original text
        # -------------------------------------------------

        "raw_text": candidate.get(
            "text",
            "",
        ),

        "medicine_text": candidate.get(
            "medicine_text",
            "",
        ),

        # -------------------------------------------------
        # Confidence
        # -------------------------------------------------

        "ocr_confidence": round(
            float(
                candidate.get(
                    "ocr_confidence",
                    0.0,
                )
            ),
            3,
        ),

        "candidate_score": round(
            float(
                candidate.get(
                    "candidate_score",
                    0.0,
                )
            ),
            3,
        ),

        # -------------------------------------------------
        # Preserve structured medicine information
        # -------------------------------------------------

        "name": candidate.get(
            "name"
        ),

        "generic_name": candidate.get(
            "generic_name"
        ),

        "brand_name": candidate.get(
            "brand_name"
        ),

        "strength_value": candidate.get(
            "strength_value"
        ),

        "strength_unit": candidate.get(
            "strength_unit"
        ),

        "strength_components": candidate.get(
            "strength_components",
            [],
        ),

        # -------------------------------------------------
        # Prescription instruction fields
        # -------------------------------------------------

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

        # -------------------------------------------------
        # Calculated information
        # -------------------------------------------------

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

        "extraction_confidence": candidate.get(
            "extraction_confidence"
        ),

        "normalization_confidence": candidate.get(
            "normalization_confidence"
        ),

        "confidence": candidate.get(
            "confidence"
        ),

        "needs_review": candidate.get(
            "needs_review"
        ),

        # -------------------------------------------------
        # Resolution
        # -------------------------------------------------

        "resolution": resolution,
    }


# ---------------------------------------------------------
# Interpret complete prescription
# ---------------------------------------------------------

def interpret_prescription(
    candidates: list[dict],
) -> dict:
    """
    Convert detected medicine candidates into a
    prescription-level intelligence result.

    This is the main entry point for the interpreter.

    The interpreter focuses on medicine identity resolution
    while preserving structured prescription information.

    Clinical safety checks such as drug interactions,
    dose limits, and other safety rules are handled by
    separate safety-analysis layers.
    """

    medicine_results: list[dict] = []

    for candidate in candidates:

        result = interpret_medicine_candidate(
            candidate
        )

        medicine_results.append(
            result
        )

    # -----------------------------------------------------
    # Count resolution outcomes
    # -----------------------------------------------------

    accepted_count = sum(
        1
        for result in medicine_results
        if result["resolution"]["status"]
        == "accepted"
    )

    review_count = sum(
        1
        for result in medicine_results
        if result["resolution"]["status"]
        == "needs_review"
    )

    unknown_count = sum(
        1
        for result in medicine_results
        if result["resolution"]["status"]
        == "unknown"
    )

    # -----------------------------------------------------
    # Determine prescription-level status
    # -----------------------------------------------------

    status = _determine_prescription_status(
        medicine_results
    )

    # -----------------------------------------------------
    # Return structured intelligence result
    # -----------------------------------------------------

    return {
        "status": status,

        "medicine_count": len(
            medicine_results
        ),

        "accepted_count": accepted_count,

        "review_required_count": (
            review_count + unknown_count
        ),

        "medicines": medicine_results,
    }