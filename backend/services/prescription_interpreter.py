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
    Determine the overall safety status of a prescription.

    Possible statuses:

        review_required
        partially_resolved
        resolved
        no_medicines_detected
    """

    if not results:
        return "no_medicines_detected"

    review_count = sum(
        1
        for result in results
        if result["resolution"]["status"] == "needs_review"
    )

    resolved_count = sum(
        1
        for result in results
        if result["resolution"]["status"] == "resolved"
    )

    if review_count == len(results):
        return "review_required"

    if review_count > 0:
        return "partially_resolved"

    if resolved_count == len(results):
        return "resolved"

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
        similarity hypotheses
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
    """

    medicine_results = []

    for candidate in candidates:

        result = interpret_medicine_candidate(
            candidate
        )

        medicine_results.append(
            result
        )

    status = _determine_prescription_status(
        medicine_results
    )

    review_count = sum(
        1
        for result in medicine_results
        if result["resolution"]["status"]
        == "needs_review"
    )

    resolved_count = sum(
        1
        for result in medicine_results
        if result["resolution"]["status"]
        == "resolved"
    )

    return {
        "status": status,

        "medicine_count": len(
            medicine_results
        ),

        "resolved_count": resolved_count,

        "review_required_count": review_count,

        "medicines": medicine_results,
    }