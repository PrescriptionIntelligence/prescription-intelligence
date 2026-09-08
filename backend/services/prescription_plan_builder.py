"""
Prescription Plan Builder

Combines resolved medicine information with interpreted
medication instructions into a structured prescription plan.

This layer does NOT:
    - diagnose
    - prescribe
    - alter the doctor's instructions
    - invent missing information

It organizes the output of the AI/ML + rule-based pipeline
into a form that can later be consumed by the API/UI.
"""

from __future__ import annotations

from backend.services.instruction_text_extractor import (
    extract_instruction_text,
)

from backend.services.instruction_interpreter import (
    interpret_instruction,
)


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def _safe_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------
# Build one medicine plan
# ---------------------------------------------------------

def build_medicine_plan(
    medicine_result: dict,
) -> dict:
    """
    Combine one interpreted medicine result with its
    medication instructions.

    Expected input:

        {
            "raw_text": ...,
            "medicine_text": ...,
            "ocr_confidence": ...,
            "candidate_score": ...,
            "resolution": ...
        }
    """

    raw_text = medicine_result.get(
        "raw_text",
        "",
    )

    resolution = medicine_result.get(
        "resolution",
        {},
    )

    # -----------------------------------------------------
    # Extract instruction text from the original item.
    # -----------------------------------------------------

    instruction_extraction = (
        extract_instruction_text(
            raw_text
        )
    )

    instruction_text = (
        instruction_extraction.get(
            "instruction_text",
            "",
        )
    )

    # -----------------------------------------------------
    # Interpret the extracted instruction.
    # -----------------------------------------------------

    if instruction_text:

        instruction = interpret_instruction(
            instruction_text
        )

    else:

        instruction = {
            "raw_text": "",
            "clean_text": "",
            "quantity": None,
            "frequency": None,
            "timing": None,
            "food_relation": None,
            "duration": None,
            "route": None,
            "confidence": 0.0,
            "needs_review": True,
        }

    # -----------------------------------------------------
    # Medicine resolution
    # -----------------------------------------------------

    top_hypothesis = resolution.get(
        "top_hypothesis"
    )

    if top_hypothesis is None:
        top_hypothesis = {}

    # -----------------------------------------------------
    # Overall review state
    #
    # A plan requires review if either:
    #
    #   medicine resolution needs review
    #   OR
    #   instruction interpretation needs review
    # -----------------------------------------------------

    medicine_needs_review = (
        resolution.get(
            "status"
        )
        != "resolved"
    )

    instruction_needs_review = bool(
        instruction.get(
            "needs_review",
            True,
        )
    )

    needs_review = (
        medicine_needs_review
        or instruction_needs_review
    )

    # -----------------------------------------------------
    # Combined confidence
    #
    # We intentionally use the weaker component rather
    # than averaging away uncertainty.
    # -----------------------------------------------------

    medicine_confidence = _safe_float(
        resolution.get(
            "evidence",
            {},
        ).get(
            "top_score",
            0.0,
        )
    )

    instruction_confidence = _safe_float(
        instruction.get(
            "confidence",
            0.0,
        )
    )

    if medicine_confidence > 0 and instruction_confidence > 0:

        overall_confidence = min(
            medicine_confidence,
            instruction_confidence,
        )

    elif medicine_confidence > 0:

        overall_confidence = medicine_confidence

    else:

        overall_confidence = instruction_confidence

    # -----------------------------------------------------
    # Final structured plan
    # -----------------------------------------------------

    return {
        "medicine": {
            "raw_text": medicine_result.get(
                "medicine_text",
                "",
            ),

            "normalized_name": top_hypothesis.get(
                "normalized_name"
            ),

            "generic_name": top_hypothesis.get(
                "generic_name"
            ),

            "strength_value": top_hypothesis.get(
                "strength_value"
            ),

            "strength_unit": top_hypothesis.get(
                "strength_unit"
            ),

            "dosage_form": top_hypothesis.get(
                "dosage_form"
            ),

            "status": resolution.get(
                "status",
                "needs_review",
            ),

            "alternatives": resolution.get(
                "alternatives",
                [],
            ),
        },

        "instructions": {
            "raw_text": instruction_extraction.get(
                "raw_text",
                "",
            ),

            "instruction_text": instruction_text,

            "quantity": instruction.get(
                "quantity"
            ),

            "frequency": instruction.get(
                "frequency"
            ),

            "timing": instruction.get(
                "timing"
            ),

            "food_relation": instruction.get(
                "food_relation"
            ),

            "duration": instruction.get(
                "duration"
            ),

            "route": instruction.get(
                "route"
            ),
        },

        "confidence": round(
            overall_confidence,
            3,
        ),

        "needs_review": needs_review,

        "review_reasons": {
            "medicine": medicine_needs_review,
            "instructions": instruction_needs_review,
        },
    }


# ---------------------------------------------------------
# Build complete prescription plan
# ---------------------------------------------------------

def build_prescription_plan(
    interpretation: dict,
) -> dict:
    """
    Build a structured prescription plan from the output
    of interpret_prescription().
    """

    medicine_results = interpretation.get(
        "medicines",
        [],
    )

    plans = []

    for medicine_result in medicine_results:

        plans.append(
            build_medicine_plan(
                medicine_result
            )
        )

    review_count = sum(
        1
        for plan in plans
        if plan["needs_review"]
    )

    resolved_count = sum(
        1
        for plan in plans
        if not plan["needs_review"]
    )

    if not plans:

        status = "no_medicines_detected"

    elif review_count == len(plans):

        status = "review_required"

    elif review_count > 0:

        status = "partially_resolved"

    else:

        status = "resolved"

    return {
        "status": status,

        "medicine_count": len(
            plans
        ),

        "resolved_count": resolved_count,

        "review_required_count": review_count,

        "medicines": plans,
    }