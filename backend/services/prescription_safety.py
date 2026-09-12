"""
Prescription Safety Analyzer

Performs conservative, prescription-level safety checks
using information already extracted by the pipeline.

This is a decision-support layer.

It does NOT:
    - diagnose
    - prescribe
    - confirm a medicine from uncertain OCR
    - replace pharmacist/doctor review
    - make unsupported clinical claims

The analyzer flags uncertainty and structural problems
for human review.
"""

from __future__ import annotations

from collections import Counter


# ---------------------------------------------------------
# Safety thresholds
# ---------------------------------------------------------

LOW_CONFIDENCE_THRESHOLD = 0.60


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def _get_resolution(
    medicine: dict,
) -> dict:
    """
    Return the medicine resolution object when available.

    The interpreter attaches the resolver output to the
    canonical medicine record. The helper remains defensive
    because older records may not contain resolution data.
    """

    resolution = medicine.get(
        "resolution"
    )

    if isinstance(resolution, dict):
        return resolution

    return {}


def _get_resolution_evidence(
    medicine: dict,
) -> dict:
    """
    Return resolver evidence when available.
    """

    resolution = _get_resolution(
        medicine
    )

    evidence = resolution.get(
        "evidence"
    )

    if isinstance(evidence, dict):
        return evidence

    return {}


# ---------------------------------------------------------
# Individual medicine checks
# ---------------------------------------------------------

def _check_medicine_resolution(
    medicine: dict,
) -> list[dict]:
    """
    Flag genuine medicine identification uncertainty.

    A strength conflict is intentionally handled separately.
    If the medicine identity itself has been resolved but the
    prescription strength conflicts with the resolved reference,
    we should report the strength problem rather than claiming
    that the medicine identity is uncertain.
    """

    issues = []

    status = medicine.get(
        "status"
    )

    resolution = _get_resolution(
        medicine
    )

    resolution_status = resolution.get(
        "status"
    )

    # The strength-aware interpreter may provide a resolved
    # medicine even when the final resolution requires review.
    # In that case, do not automatically label the identity
    # as uncertain if the reason is specifically strength conflict.
    resolution_reason = resolution.get(
        "reason"
    )

    if (
        resolution_reason == "strength_conflict"
        or resolution.get("status") == "needs_review"
        and _get_resolution_evidence(medicine).get(
            "strength_compatible"
        ) is False
    ):
        return issues

    if (
        status != "resolved"
        and resolution_status not in {
            "accepted",
        }
    ):

        issues.append(
            {
                "type": "medicine_identification_uncertain",
                "severity": "high",
                "message": (
                    "Medicine identity could not be "
                    "confirmed confidently."
                ),
            }
        )

    return issues


# ---------------------------------------------------------
# Strength checks
# ---------------------------------------------------------

def _check_strength(
    medicine: dict,
) -> list[dict]:
    """
    Flag missing medicine strength and explicit conflicts
    between the prescription strength and the resolved
    medicine reference strength.
    """

    issues = []

    strength_value = medicine.get(
        "strength_value"
    )

    strength_unit = medicine.get(
        "strength_unit"
    )

    if (
        strength_value is None
        or not strength_unit
    ):

        issues.append(
            {
                "type": "strength_missing",
                "severity": "medium",
                "message": (
                    "Medicine strength is missing "
                    "or could not be determined."
                ),
            }
        )

        return issues

    evidence = _get_resolution_evidence(
        medicine
    )

    strength_compatible = evidence.get(
        "strength_compatible"
    )

    strength_reason = evidence.get(
        "strength_reason"
    )

    if (
        strength_compatible is False
        or (
            isinstance(strength_reason, str)
            and strength_reason.startswith(
                "strength_conflict:"
            )
        )
    ):

        resolution = _get_resolution(
            medicine
        )

        top_hypothesis = resolution.get(
            "top_hypothesis"
        )

        if not isinstance(
            top_hypothesis,
            dict,
        ):
            top_hypothesis = {}

        reference_value = top_hypothesis.get(
            "strength_value"
        )

        reference_unit = top_hypothesis.get(
            "strength_unit"
        )

        if (
            reference_value is not None
            and reference_unit
        ):
            message = (
                f"Prescription strength is "
                f"{strength_value} {strength_unit}, "
                f"but the resolved medicine reference "
                f"indicates {reference_value} "
                f"{reference_unit}. Verify the prescribed "
                f"strength before dispensing or clinical use."
            )
        else:
            message = (
                "The extracted medicine strength conflicts "
                "with the resolved medicine reference. "
                "Verify the prescribed strength before "
                "dispensing or clinical use."
            )

        issues.append(
            {
                "type": "strength_conflict",
                "severity": "high",
                "message": message,
                "prescription_strength": (
                    f"{strength_value} {strength_unit}"
                ),
                "reference_strength": (
                    f"{reference_value} {reference_unit}"
                    if (
                        reference_value is not None
                        and reference_unit
                    )
                    else None
                ),
                "resolution_reason": strength_reason,
            }
        )

    return issues


# ---------------------------------------------------------
# Instruction checks
# ---------------------------------------------------------

def _check_instructions(
    medicine_plan: dict,
) -> list[dict]:
    """
    Flag incomplete or uncertain medication instructions.

    Generic medicine review state is NOT treated as evidence
    that instructions themselves are uncertain.

    Instruction uncertainty must be explicitly represented
    by instruction-level review fields.
    """

    issues = []

    instructions = medicine_plan.get(
        "instructions",
        {},
    )

    if not instructions:
        return [
            {
                "type": "instructions_missing",
                "severity": "high",
                "message": (
                    "Medication instructions could "
                    "not be extracted."
                ),
            }
        ]

    # -----------------------------------------------------
    # Instruction-specific review state
    # -----------------------------------------------------

    instruction_review_required = (
        medicine_plan.get(
            "instruction_review_required"
        )
    )

    if instruction_review_required is None:
        instruction_review_required = (
            medicine_plan.get(
                "instructions_needs_review"
            )
        )

    if instruction_review_required is True:

        issues.append(
            {
                "type": "instructions_uncertain",
                "severity": "high",
                "message": (
                    "Medication instructions require "
                    "human review."
                ),
            }
        )

    # -----------------------------------------------------
    # Required instruction fields
    # -----------------------------------------------------

    quantity = instructions.get(
        "quantity"
    )

    frequency = instructions.get(
        "frequency"
    )

    duration = instructions.get(
        "duration"
    )

    route = instructions.get(
        "route"
    )

    if quantity is None:

        issues.append(
            {
                "type": "quantity_missing",
                "severity": "medium",
                "message": (
                    "Medication quantity could "
                    "not be determined."
                ),
            }
        )

    if frequency is None:

        issues.append(
            {
                "type": "frequency_missing",
                "severity": "medium",
                "message": (
                    "Medication frequency could "
                    "not be determined."
                ),
            }
        )

    # Duration and route remain informational/low-severity
    # when they are genuinely absent. They do not by
    # themselves make an otherwise resolved plan unsafe.

    if duration is None:

        issues.append(
            {
                "type": "duration_missing",
                "severity": "low",
                "message": (
                    "Medication duration was not "
                    "specified or could not be determined."
                ),
            }
        )

    if route is None:

        issues.append(
            {
                "type": "route_missing",
                "severity": "low",
                "message": (
                    "Medication route was not "
                    "specified or could not be determined."
                ),
            }
        )

    return issues


# ---------------------------------------------------------
# Confidence check
# ---------------------------------------------------------

def _check_confidence(
    medicine_plan: dict,
) -> list[dict]:

    confidence = medicine_plan.get(
        "confidence",
        0.0,
    )

    try:
        confidence = float(
            confidence
        )
    except (
        TypeError,
        ValueError,
    ):
        confidence = 0.0

    if confidence < LOW_CONFIDENCE_THRESHOLD:

        return [
            {
                "type": "low_confidence",
                "severity": "high",
                "message": (
                    "Overall extraction confidence "
                    "is low."
                ),
            }
        ]

    return []


# ---------------------------------------------------------
# Duplicate medicine check
# ---------------------------------------------------------

def _check_duplicate_medicines(
    medicines: list[dict],
) -> list[dict]:

    issues = []

    names = []

    for medicine_plan in medicines:

        medicine = medicine_plan.get(
            "medicine",
            {},
        )

        name = medicine.get(
            "normalized_name"
        )

        if name:
            names.append(
                name.strip().lower()
            )

    counts = Counter(
        names
    )

    for name, count in counts.items():

        if count > 1:

            issues.append(
                {
                    "type": "duplicate_medicine",
                    "severity": "medium",
                    "medicine": name,
                    "message": (
                        "The same normalized medicine "
                        "appears multiple times."
                    ),
                }
            )

    return issues


# ---------------------------------------------------------
# Analyze one medicine
# ---------------------------------------------------------

def analyze_medicine_plan(
    medicine_plan: dict,
) -> dict:

    medicine = medicine_plan.get(
        "medicine",
        {},
    )

    issues = []

    issues.extend(
        _check_medicine_resolution(
            medicine
        )
    )

    issues.extend(
        _check_strength(
            medicine
        )
    )

    issues.extend(
        _check_instructions(
            medicine_plan
        )
    )

    issues.extend(
        _check_confidence(
            medicine_plan
        )
    )

    return {
        "medicine": medicine.get(
            "normalized_name"
        ),

        "issue_count": len(
            issues
        ),

        "issues": issues,

        "needs_review": bool(
            issues
        ),
    }


# ---------------------------------------------------------
# Prescription-level analysis
# ---------------------------------------------------------

def analyze_prescription_safety(
    prescription_plan: dict,
) -> dict:
    """
    Analyze an entire prescription plan.
    """

    medicines = prescription_plan.get(
        "medicines",
        [],
    )

    medicine_reports = []

    for medicine_plan in medicines:

        medicine_reports.append(
            analyze_medicine_plan(
                medicine_plan
            )
        )

    duplicate_issues = (
        _check_duplicate_medicines(
            medicines
        )
    )

    all_issues = []

    for report in medicine_reports:

        all_issues.extend(
            report["issues"]
        )

    all_issues.extend(
        duplicate_issues
    )

    high_count = sum(
        1
        for issue in all_issues
        if issue.get("severity")
        == "high"
    )

    medium_count = sum(
        1
        for issue in all_issues
        if issue.get("severity")
        == "medium"
    )

    low_count = sum(
        1
        for issue in all_issues
        if issue.get("severity")
        == "low"
    )

    if high_count > 0:

        safety_status = "review_required"

    elif medium_count > 0:

        safety_status = "caution"

    elif low_count > 0:

        safety_status = "informational"

    else:

        safety_status = "no_structural_issues_detected"

    return {
        "safety_status": safety_status,

        "medicine_count": len(
            medicines
        ),

        "issue_count": len(
            all_issues
        ),

        "high_severity_count": high_count,

        "medium_severity_count": medium_count,

        "low_severity_count": low_count,

        "medicines": medicine_reports,

        "prescription_issues": duplicate_issues,
    }
