"""
Prescription Plan Builder

Combines resolved medicine information with interpreted
medication instructions into a structured prescription plan.

This layer does NOT:
    - diagnose
    - prescribe
    - alter the doctor's instructions
    - invent missing information

It organizes information already extracted by the prescription
pipeline and combines it with the medicine resolution layer.
"""

from __future__ import annotations

import re

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


def _is_positive_number(value) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def _normalize_resolution_status(status: str | None) -> str:
    """
    Normalize medicine-resolution status into the canonical
    plan-level vocabulary.

    The medicine interpreter may use 'accepted', while the
    plan/safety layers use 'resolved'.

    Canonical values:
        resolved
        needs_review
        unknown
    """

    if status in {
        "accepted",
        "resolved",
    }:
        return "resolved"

    if status in {
        "needs_review",
        "review_required",
        "partially_resolved",
    }:
        return "needs_review"

    return "unknown"


def _extract_quantity_from_raw_text(
    text: str,
) -> int | float | None:
    """
    Recover an explicit dosage quantity from the original
    prescription text.

    Examples:
        1 tablet
        2 tablets
        0.5 tablet
        half tablet
    """

    if not text:
        return None

    match = re.search(
        r"\b(\d+(?:\.\d+)?)\s*"
        r"(tablet|tablets|tab|tabs|capsule|capsules|cap|caps)\b",
        text,
        flags=re.IGNORECASE,
    )

    if match:
        value = float(match.group(1))

        if value.is_integer():
            return int(value)

        return value

    if re.search(
        r"\bhalf\s*(tablet|tab|capsule|cap)\b",
        text,
        flags=re.IGNORECASE,
    ):
        return 0.5

    return None


def _extract_dose_unit_from_raw_text(
    text: str,
) -> str | None:
    """
    Recover the unit associated with an explicit dosage
    quantity in the original prescription text.
    """

    if not text:
        return None

    match = re.search(
        r"\b\d+(?:\.\d+)?\s*"
        r"(tablet|tablets|tab|tabs|capsule|capsules|cap|caps)\b",
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        if re.search(
            r"\bhalf\s*(tablet|tab|capsule|cap)\b",
            text,
            flags=re.IGNORECASE,
        ):
            return "tablet"

        return None

    unit = match.group(1).lower()

    if unit in {"tab", "tabs", "tablet", "tablets"}:
        return "tablet"

    if unit in {"cap", "caps", "capsule", "capsules"}:
        return "capsule"

    return unit


def _infer_dosage_form(
    medicine_result: dict,
    top_hypothesis: dict,
) -> str | None:
    """
    Determine dosage form using prescription evidence first.

    Explicit prescription information takes precedence over
    knowledge-base information.
    """

    explicit_unit = medicine_result.get(
        "dose_unit"
    )

    if explicit_unit:
        normalized = str(
            explicit_unit
        ).strip().lower()

        if normalized in {
            "tablet",
            "tablets",
            "tab",
            "tabs",
        }:
            return "Tablet"

        if normalized in {
            "capsule",
            "capsules",
            "cap",
            "caps",
        }:
            return "Capsule"

        return str(
            explicit_unit
        ).strip()

    raw_text = medicine_result.get(
        "raw_text",
        "",
    )

    raw_unit = _extract_dose_unit_from_raw_text(
        raw_text
    )

    if raw_unit:
        if raw_unit == "tablet":
            return "Tablet"

        if raw_unit == "capsule":
            return "Capsule"

        return raw_unit

    return top_hypothesis.get(
        "dosage_form"
    )


def _resolve_quantity(
    medicine_result: dict,
    instruction: dict,
) -> int | float | None:
    """
    Preserve quantity from the strongest available source.

    Priority:
        1. structured extraction
        2. instruction interpreter
        3. original raw prescription text
    """

    extracted_quantity = medicine_result.get(
        "dose_value"
    )

    if _is_positive_number(
        extracted_quantity
    ):
        return extracted_quantity

    interpreted_quantity = instruction.get(
        "quantity"
    )

    if _is_positive_number(
        interpreted_quantity
    ):
        return interpreted_quantity

    return _extract_quantity_from_raw_text(
        medicine_result.get(
            "raw_text",
            "",
        )
    )


def _resolve_route(
    medicine_result: dict,
    instruction: dict,
) -> str | None:
    """
    Preserve route information already extracted upstream.

    Priority:
        1. structured extraction
        2. instruction interpreter
    """

    extracted_route = medicine_result.get(
        "route"
    )

    if extracted_route:
        return extracted_route

    return instruction.get(
        "route"
    )


def _resolve_frequency(
    medicine_result: dict,
    instruction: dict,
) -> str | None:
    """
    Preserve structured frequency extraction when available.
    """

    extracted_frequency = medicine_result.get(
        "frequency_value"
    )

    extracted_frequency_unit = medicine_result.get(
        "frequency_unit"
    )

    if (
        extracted_frequency is not None
        and extracted_frequency_unit
    ):
        try:
            numeric_frequency = float(
                extracted_frequency
            )

            if numeric_frequency == 1:
                return "once_daily"

            if numeric_frequency == 2:
                return "twice_daily"

            if numeric_frequency == 3:
                return "three_times_daily"

            if numeric_frequency == 4:
                return "four_times_daily"

        except (TypeError, ValueError):
            pass

    return instruction.get(
        "frequency"
    )


def _resolve_duration(
    medicine_result: dict,
    instruction: dict,
) -> dict | None:
    """
    Preserve structured duration extraction when available.
    """

    extracted_value = medicine_result.get(
        "duration_value"
    )

    extracted_unit = medicine_result.get(
        "duration_unit"
    )

    if (
        extracted_value is not None
        and extracted_unit
    ):
        return {
            "value": extracted_value,
            "unit": extracted_unit,
            "text": (
                f"{extracted_value} "
                f"{extracted_unit}"
            ),
        }

    return instruction.get(
        "duration"
    )


def _resolve_strength(
    medicine_result: dict,
    top_hypothesis: dict,
) -> tuple[object, str | None]:
    """
    Resolve medicine strength using prescription evidence first.

    Priority:
        1. explicit structured prescription strength
        2. resolved medicine hypothesis strength

    The prescription value must not be silently replaced by
    knowledge-base or resolver defaults.
    """

    explicit_strength_value = medicine_result.get(
        "strength_value"
    )

    explicit_strength_unit = medicine_result.get(
        "strength_unit"
    )

    resolved_strength_value = top_hypothesis.get(
        "strength_value"
    )

    resolved_strength_unit = top_hypothesis.get(
        "strength_unit"
    )

    if explicit_strength_value is not None:
        return (
            explicit_strength_value,
            explicit_strength_unit
            or resolved_strength_unit,
        )

    return (
        resolved_strength_value,
        resolved_strength_unit,
    )


# ---------------------------------------------------------
# Build one medicine plan
# ---------------------------------------------------------

def build_medicine_plan(
    medicine_result: dict,
) -> dict:
    """
    Combine one interpreted medicine result with its
    medication instructions.

    Resolution metadata is deliberately preserved inside
    the medicine plan so downstream safety analysis can
    distinguish medicine-identity uncertainty from
    strength conflicts and other resolution conditions.
    """

    raw_text = medicine_result.get(
        "raw_text",
        "",
    )

    resolution = medicine_result.get(
        "resolution",
        {},
    )

    if not isinstance(
        resolution,
        dict,
    ):
        resolution = {}

    top_hypothesis = resolution.get(
        "top_hypothesis"
    )

    if not isinstance(
        top_hypothesis,
        dict,
    ):
        top_hypothesis = {}

    # -----------------------------------------------------
    # Resolve explicit prescription strength
    # -----------------------------------------------------

    strength_value, strength_unit = _resolve_strength(
        medicine_result,
        top_hypothesis,
    )

    # -----------------------------------------------------
    # Extract instruction text
    # -----------------------------------------------------

    instruction_extraction = extract_instruction_text(
        raw_text
    )

    instruction_text = instruction_extraction.get(
        "instruction_text",
        "",
    )

    # -----------------------------------------------------
    # Interpret instructions
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
    # Preserve structured extraction
    # -----------------------------------------------------

    quantity = _resolve_quantity(
        medicine_result,
        instruction,
    )

    frequency = _resolve_frequency(
        medicine_result,
        instruction,
    )

    duration = _resolve_duration(
        medicine_result,
        instruction,
    )

    route = _resolve_route(
        medicine_result,
        instruction,
    )

    dosage_form = _infer_dosage_form(
        medicine_result,
        top_hypothesis,
    )

    # -----------------------------------------------------
    # Canonical medicine resolution
    # -----------------------------------------------------

    raw_resolution_status = resolution.get(
        "status"
    )

    medicine_status = _normalize_resolution_status(
        raw_resolution_status
    )

    # -----------------------------------------------------
    # Determine whether medicine identification needs review
    # -----------------------------------------------------

    medicine_needs_review = (
        medicine_status != "resolved"
    )

    # -----------------------------------------------------
    # Determine whether instructions need review
    # -----------------------------------------------------

    has_quantity = (
        quantity is not None
    )

    has_frequency = (
        frequency is not None
    )

    has_duration = (
        duration is not None
    )

    instruction_text_present = bool(
        instruction_text.strip()
    )

    instruction_needs_review = (
        not instruction_text_present
        or not has_quantity
        or not has_frequency
    )

    raw_duration_present = bool(
        re.search(
            r"\b\d+\s*(day|days|week|weeks|month|months)\b",
            raw_text,
            flags=re.IGNORECASE,
        )
    )

    if raw_duration_present and not has_duration:
        instruction_needs_review = True

    needs_review = (
        medicine_needs_review
        or instruction_needs_review
    )

    # -----------------------------------------------------
    # Confidence
    # -----------------------------------------------------

    resolution_evidence = resolution.get(
        "evidence",
        {},
    )

    if not isinstance(
        resolution_evidence,
        dict,
    ):
        resolution_evidence = {}

    medicine_confidence = _safe_float(
        resolution_evidence.get(
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

    structured_signal_count = sum(
        value is not None
        for value in [
            quantity,
            frequency,
            duration,
            route,
        ]
    )

    if structured_signal_count >= 4:
        instruction_confidence = max(
            instruction_confidence,
            0.90,
        )
    elif structured_signal_count >= 3:
        instruction_confidence = max(
            instruction_confidence,
            0.80,
        )

    if (
        medicine_confidence > 0
        and instruction_confidence > 0
    ):

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

            "strength_value": strength_value,

            "strength_unit": strength_unit,

            "dosage_form": dosage_form,

            "status": medicine_status,

            "alternatives": resolution.get(
                "alternatives",
                [],
            ),

            # Preserve the complete resolver output for
            # downstream clinical safety analysis.
            "resolution": resolution,

            "resolution_status": resolution.get(
                "status"
            ),

            "resolution_reason": resolution.get(
                "reason"
            ),

            "resolution_evidence": resolution_evidence,

            "top_hypothesis": top_hypothesis,
        },

        "instructions": {
            "raw_text": instruction_extraction.get(
                "raw_text",
                "",
            ),

            "instruction_text": instruction_text,

            "quantity": quantity,

            "frequency": frequency,

            "timing": instruction.get(
                "timing"
            ),

            "food_relation": instruction.get(
                "food_relation"
            ),

            "duration": duration,

            "route": route,
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
