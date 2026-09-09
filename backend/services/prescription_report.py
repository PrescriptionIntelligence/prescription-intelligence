"""
Prescription Report

Converts prescription safety analysis into a clean,
frontend/API-friendly report.

This layer does NOT:
    - diagnose
    - prescribe
    - confirm uncertain medicines
    - invent missing instructions

It only summarizes existing intelligence and safety findings.
"""

from __future__ import annotations


# ---------------------------------------------------------
# Severity ordering
# ---------------------------------------------------------

SEVERITY_ORDER = {
    "high": 3,
    "medium": 2,
    "low": 1,
}


# ---------------------------------------------------------
# Human-readable labels
# ---------------------------------------------------------

ISSUE_LABELS = {
    "medicine_identification_uncertain": (
        "Medicine identification is uncertain"
    ),
    "instructions_uncertain": (
        "Medication instructions require review"
    ),
    "instructions_missing": (
        "Medication instructions are missing"
    ),
    "quantity_missing": (
        "Quantity could not be determined"
    ),
    "frequency_missing": (
        "Frequency could not be determined"
    ),
    "duration_missing": (
        "Duration could not be determined"
    ),
    "route_missing": (
        "Route could not be determined"
    ),
    "strength_missing": (
        "Medicine strength is missing"
    ),
    "missing_strength": (
        "Medicine strength is missing"
    ),
    "missing_medicine_name": (
        "Medicine name could not be identified"
    ),
    "missing_dose": (
        "Dose could not be determined"
    ),
    "missing_frequency": (
        "Frequency could not be determined"
    ),
    "invalid_strength": (
        "Medicine strength is invalid"
    ),
    "invalid_dose": (
        "Medicine dose is invalid"
    ),
    "invalid_frequency": (
        "Medicine frequency is invalid"
    ),
    "invalid_daily_dose": (
        "Calculated daily dose is invalid"
    ),
    "daily_dose_not_calculated": (
        "Daily dose could not be calculated"
    ),
    "invalid_daily_dose_components": (
        "Calculated daily-dose components are invalid"
    ),
    "low_extraction_confidence": (
        "Medicine extraction confidence is low"
    ),
    "low_normalization_confidence": (
        "Medicine normalization confidence is low"
    ),
    "low_confidence": (
        "Overall confidence is low"
    ),
    "ambiguous_medicine": (
        "Medicine identification is ambiguous"
    ),
    "low_identification_confidence": (
        "Medicine identification confidence is low"
    ),
    "duplicate_medicine": (
        "Duplicate medicine detected"
    ),
    "drug_interaction": (
        "Potential drug interaction detected"
    ),
    "daily_dose_limit_exceeded": (
        "Reference daily-dose limit exceeded"
    ),
    "poor_ocr_quality": (
        "OCR quality is poor"
    ),
    "ocr_extraction_failed": (
        "Medicine extraction failed"
    ),
}


# ---------------------------------------------------------
# Issue formatting
# ---------------------------------------------------------


def _format_issue(
    issue: dict,
) -> dict:
    """
    Convert one safety issue into a clean report item.
    """

    issue_type = issue.get(
        "type",
        "unknown_issue",
    )

    severity = issue.get(
        "severity",
        "low",
    )

    # Keep the report contract strict.
    if severity not in SEVERITY_ORDER:
        severity = "low"

    return {
        "type": issue_type,
        "severity": severity,
        "title": ISSUE_LABELS.get(
            issue_type,
            issue_type.replace(
                "_",
                " ",
            ).capitalize(),
        ),
        "message": issue.get(
            "message",
            "",
        ),
    }


# ---------------------------------------------------------
# Medicine report
# ---------------------------------------------------------


def _build_medicine_report(
    medicine_result: dict,
) -> dict:
    """
    Build a clean report for one medicine.
    """

    medicine_name = medicine_result.get(
        "medicine",
        "Unknown medicine",
    )

    issues = medicine_result.get(
        "issues",
        [],
    )

    formatted_issues = [
        _format_issue(issue)
        for issue in issues
    ]

    formatted_issues.sort(
        key=lambda issue: SEVERITY_ORDER.get(
            issue["severity"],
            0,
        ),
        reverse=True,
    )

    high_count = sum(
        1
        for issue in formatted_issues
        if issue["severity"] == "high"
    )

    medium_count = sum(
        1
        for issue in formatted_issues
        if issue["severity"] == "medium"
    )

    low_count = sum(
        1
        for issue in formatted_issues
        if issue["severity"] == "low"
    )

    return {
        "medicine": medicine_name,
        "needs_review": bool(
            medicine_result.get(
                "needs_review",
                False,
            )
        ),
        "issue_count": len(
            formatted_issues
        ),
        "severity": {
            "high": high_count,
            "medium": medium_count,
            "low": low_count,
        },
        "issues": formatted_issues,
    }


# ---------------------------------------------------------
# Summary generation
# ---------------------------------------------------------


def _build_summary(
    safety_analysis: dict,
) -> dict:
    """
    Build prescription-level safety summary.
    """

    medicine_count = int(
        safety_analysis.get(
            "medicine_count",
            0,
        )
    )

    issue_count = int(
        safety_analysis.get(
            "issue_count",
            0,
        )
    )

    high_count = int(
        safety_analysis.get(
            "high_severity_count",
            0,
        )
    )

    medium_count = int(
        safety_analysis.get(
            "medium_severity_count",
            0,
        )
    )

    low_count = int(
        safety_analysis.get(
            "low_severity_count",
            0,
        )
    )

    if high_count > 0:

        message = (
            "Human review is required before this "
            "prescription can be considered reliable."
        )

    elif medium_count > 0:

        message = (
            "Some prescription details require "
            "human verification."
        )

    elif issue_count > 0:

        message = (
            "Minor prescription information is "
            "incomplete."
        )

    elif medicine_count > 0:

        message = (
            "No immediate interpretation issues "
            "were detected."
        )

    else:

        message = (
            "No medicines were detected."
        )

    return {
        "message": message,
        "medicine_count": medicine_count,
        "issue_count": issue_count,
        "high_severity_count": high_count,
        "medium_severity_count": medium_count,
        "low_severity_count": low_count,
    }


# ---------------------------------------------------------
# Main report builder
# ---------------------------------------------------------


def build_prescription_report(
    safety_analysis: dict,
) -> dict:
    """
    Build the final prescription intelligence report.

    Input:
        Output from analyze_prescription_safety()

    Output:
        Clean, structured report suitable for
        API responses and frontend rendering.
    """

    medicines = safety_analysis.get(
        "medicines",
        [],
    )

    medicine_reports = [
        _build_medicine_report(
            medicine
        )
        for medicine in medicines
    ]

    summary = _build_summary(
        safety_analysis
    )

    prescription_issues = [
        _format_issue(issue)
        for issue in safety_analysis.get(
            "prescription_issues",
            [],
        )
    ]

    high_count = summary[
        "high_severity_count"
    ]

    if high_count > 0:

        overall_status = (
            "review_required"
        )

    elif summary["issue_count"] > 0:

        overall_status = (
            "review_recommended"
        )

    elif summary["medicine_count"] > 0:

        overall_status = "clear"

    else:

        overall_status = (
            "no_medicines_detected"
        )

    return {
        "overall_status": overall_status,
        "safety_status": safety_analysis.get(
            "safety_status",
            "review_required",
        ),
        "summary": summary,
        "medicines": medicine_reports,
        "prescription_issues": prescription_issues,
    }