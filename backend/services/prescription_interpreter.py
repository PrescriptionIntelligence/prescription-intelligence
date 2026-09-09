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
        "accepted" refers to medicine identity resolution.

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
        "raw_text": candidate.get(
            "text",
            "",
        ),

        "medicine_text": candidate.get(
            "medicine_text",
            "",
        ),

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

    The interpreter focuses on medicine identity resolution.
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