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
# Individual medicine checks
# ---------------------------------------------------------

def _check_medicine_resolution(
    medicine: dict,
) -> list[dict]:
    """
    Flag medicine identification uncertainty.
    """

    issues = []

    status = medicine.get(
        "status"
    )

    if status != "resolved":

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


def _check_strength(
    medicine: dict,
) -> list[dict]:
    """
    Flag missing medicine strength.
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


# ---------------------------------------------------------
# Instruction checks
# ---------------------------------------------------------

def _check_instructions(
    medicine_plan: dict,
) -> list[dict]:
    """
    Flag incomplete or uncertain medication instructions.

    The prescription plan is the source of truth here.

    The plan builder combines:
        - parser-extracted structured fields
        - instruction interpretation
        - medicine resolution

    Therefore the safety analyzer should evaluate the
    complete medicine plan rather than expecting the
    instruction sub-dictionary to contain plan-level
    review state.
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
    # Plan-level review state
    # -----------------------------------------------------

    plan_needs_review = medicine_plan.get(
        "needs_review"
    )

    if plan_needs_review is True:

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