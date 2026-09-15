"""
Prescription Report

Builds a clean, structured prescription intelligence report.

This layer:
    - summarizes existing prescription intelligence
    - formats safety findings
    - prepares data for API/frontend/PDF rendering

This layer does NOT:
    - diagnose
    - prescribe
    - confirm uncertain medicines
    - invent missing instructions
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


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
# Helpers
# ---------------------------------------------------------


def _safe_int(
    value: Any,
    default: int = 0,
) -> int:
    """
    Convert a value to int without allowing malformed
    report data to break report generation.
    """

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(
    value: Any,
    default: float | None = None,
) -> float | None:
    """
    Convert a value to float safely.
    """

    if value is None:
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clean_text(
    value: Any,
    default: str = "",
) -> str:
    """
    Convert arbitrary values into clean report text.
    """

    if value is None:
        return default

    text = str(value).strip()

    return text if text else default


# ---------------------------------------------------------
# Issue formatting
# ---------------------------------------------------------


def _format_issue(
    issue: dict,
) -> dict:
    """
    Convert one safety issue into a clean report item.
    """

    issue_type = _clean_text(
        issue.get("type"),
        "unknown_issue",
    )

    severity = _clean_text(
        issue.get("severity"),
        "low",
    ).lower()

    if severity not in SEVERITY_ORDER:
        severity = "low"

    title = ISSUE_LABELS.get(
        issue_type,
        issue_type.replace(
            "_",
            " ",
        ).capitalize(),
    )

    return {
        "type": issue_type,
        "severity": severity,
        "title": title,
        "medicine": issue.get("medicine"),
        "message": _clean_text(
            issue.get("message"),
            "No additional information was provided.",
        ),
    }


# ---------------------------------------------------------
# Medicine report
# ---------------------------------------------------------


def _medicine_display_confidence(
    source_medicine: dict | None,
) -> float | None:
    """
    Compute the displayed intelligence confidence for one
    medicine using the same formula used by the frontend:

        (extraction_confidence + normalization_confidence) / 2

    Falls back to None when neither value is available.
    """

    if not isinstance(source_medicine, dict):
        return None

    extraction = _safe_float(
        source_medicine.get("extraction_confidence")
    )

    normalization = _safe_float(
        source_medicine.get("normalization_confidence")
    )

    values = [
        v for v in (extraction, normalization)
        if v is not None
    ]

    if not values:
        return None

    return round(sum(values) / len(values), 3)


def _build_medicine_report(
    medicine_result: dict,
    plan_result: dict | None = None,
    source_medicine: dict | None = None,
) -> dict:
    """
    Build a clean report for one medicine.

    Safety information comes from medicine_result.
    Structured medication information comes from plan_result
    when available.
    source_medicine is the raw pipeline medicine record that
    carries extraction_confidence and normalization_confidence
    for computing the displayed intelligence confidence.
    """

    if not isinstance(medicine_result, dict):
        medicine_result = {}

    if not isinstance(plan_result, dict):
        plan_result = {}

    plan_medicine = plan_result.get(
        "medicine",
        {},
    )

    if not isinstance(plan_medicine, dict):
        plan_medicine = {}

    plan_instructions = plan_result.get(
        "instructions",
        {},
    )

    if not isinstance(plan_instructions, dict):
        plan_instructions = {}

    # -----------------------------------------------------
    # Medicine identity
    # -----------------------------------------------------

    medicine_name = _clean_text(
        plan_medicine.get("normalized_name")
        or medicine_result.get("medicine")
        or plan_medicine.get("generic_name"),
        "Unknown medicine",
    )

    # -----------------------------------------------------
    # Strength
    # -----------------------------------------------------

    strength_value = plan_medicine.get(
        "strength_value"
    )

    strength_unit = _clean_text(
        plan_medicine.get(
            "strength_unit"
        )
    )

    if (
        strength_value is not None
        and strength_unit
    ):
        strength = (
            f"{strength_value} {strength_unit}"
        )
    else:
        strength = medicine_result.get(
            "strength"
        )

    # -----------------------------------------------------
    # Dose
    # -----------------------------------------------------

    quantity = plan_instructions.get(
        "quantity"
    )

    dosage_form = _clean_text(
        plan_medicine.get(
            "dosage_form"
        )
    )

    if quantity is not None:

        quantity_text = _clean_text(
            quantity
        )

        if dosage_form:
            dose = (
                f"{quantity_text} "
                f"{dosage_form.lower()}"
            )
        else:
            dose = quantity_text

    else:

        dose = medicine_result.get(
            "dose"
        )

    # -----------------------------------------------------
    # Route
    # -----------------------------------------------------

    route = (
        plan_instructions.get("route")
        or medicine_result.get("route")
    )

    # -----------------------------------------------------
    # Frequency
    # -----------------------------------------------------

    frequency = (
        plan_instructions.get(
            "frequency"
        )
        or medicine_result.get(
            "frequency"
        )
    )

    frequency_labels = {
        "once_daily": "Once daily",
        "twice_daily": "Twice daily",
        "three_times_daily": "Three times daily",
        "four_times_daily": "Four times daily",
    }

    if frequency in frequency_labels:
        frequency = frequency_labels[
            frequency
        ]

    # -----------------------------------------------------
    # Duration
    # -----------------------------------------------------

    duration_data = plan_instructions.get(
        "duration"
    )

    if isinstance(
        duration_data,
        dict,
    ):

        duration = duration_data.get(
            "text"
        )

        if not duration:

            value = duration_data.get(
                "value"
            )

            unit = duration_data.get(
                "unit"
            )

            if value is not None and unit:
                duration = (
                    f"{value} {unit}"
                )

    else:

        duration = duration_data

    if not duration:
        duration = medicine_result.get(
            "duration"
        )

    # -----------------------------------------------------
    # Safety issues
    # -----------------------------------------------------

    issues = medicine_result.get(
        "issues",
        [],
    )

    if not isinstance(
        issues,
        list,
    ):
        issues = []

    formatted_issues = [
        _format_issue(issue)
        for issue in issues
        if isinstance(issue, dict)
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

    # -----------------------------------------------------
    # Review / confidence
    # -----------------------------------------------------

    needs_review = bool(
        plan_result.get(
            "needs_review",
            medicine_result.get(
                "needs_review",
                False,
            ),
        )
    )

    # Displayed intelligence confidence uses the same
    # definition as the frontend and the overall report:
    #     (extraction_confidence + normalization_confidence) / 2
    # source_medicine is the raw pipeline record that carries
    # those values.  Fall back to plan confidence only when
    # the source medicine is unavailable (e.g. legacy data).
    confidence = _medicine_display_confidence(source_medicine)

    if confidence is None:
        confidence = _safe_float(
            plan_result.get("confidence")
        )

    if confidence is None:
        confidence = _safe_float(
            medicine_result.get("confidence")
        )

    return {
        "medicine": medicine_name,

        "generic_name": (
            plan_medicine.get(
                "generic_name"
            )
            or medicine_result.get(
                "generic_name"
            )
        ),

        "brand_name": medicine_result.get(
            "brand_name"
        ),

        "strength": strength,

        "dose": dose,

        "route": route,

        "frequency": frequency,

        "duration": duration,

        "dosage_form": dosage_form,

        "needs_review": needs_review,

        "confidence": confidence,

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

    medicine_count = _safe_int(
        safety_analysis.get(
            "medicine_count",
            0,
        )
    )

    issue_count = _safe_int(
        safety_analysis.get(
            "issue_count",
            0,
        )
    )

    high_count = _safe_int(
        safety_analysis.get(
            "high_severity_count",
            0,
        )
    )

    medium_count = _safe_int(
        safety_analysis.get(
            "medium_severity_count",
            0,
        )
    )

    low_count = _safe_int(
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
# Overall status
# ---------------------------------------------------------


def _determine_overall_status(
    summary: dict,
) -> str:
    """
    Determine the report-level status.
    """

    high_count = summary[
        "high_severity_count"
    ]

    issue_count = summary[
        "issue_count"
    ]

    medicine_count = summary[
        "medicine_count"
    ]

    if high_count > 0:
        return "review_required"

    if issue_count > 0:
        return "review_recommended"

    if medicine_count > 0:
        return "clear"

    return "no_medicines_detected"


# ---------------------------------------------------------
# Overall intelligence confidence
# ---------------------------------------------------------


def _compute_overall_confidence(
    medicines: list[dict],
) -> float | None:
    """
    Compute overall intelligence confidence using the same
    medicine-level confidence model used by the frontend.

    For each medicine:
        overall medicine confidence =
            average(extraction_confidence,
                    normalization_confidence)

    Prescription-level confidence is then the average of
    the available medicine-level confidence values.

    Returns a 0..1 value.
    """

    if not medicines:
        return None

    medicine_confidences = []

    for medicine in medicines:
        if not isinstance(
            medicine,
            dict,
        ):
            continue

        values = []

        extraction_confidence = _safe_float(
            medicine.get(
                "extraction_confidence"
            )
        )

        normalization_confidence = _safe_float(
            medicine.get(
                "normalization_confidence"
            )
        )

        if extraction_confidence is not None:
            values.append(
                extraction_confidence
            )

        if normalization_confidence is not None:
            values.append(
                normalization_confidence
            )

        if not values:
            continue

        medicine_confidences.append(
            sum(values) / len(values)
        )

    if not medicine_confidences:
        return None

    return round(
        sum(medicine_confidences)
        / len(medicine_confidences),
        3,
    )


# ---------------------------------------------------------
# Main report builder
# ---------------------------------------------------------


def build_prescription_report(
    safety_analysis: dict,
    *,
    prescription_id: str | None = None,
    file_name: str | None = None,
    raw_text: str | None = None,
    analysis_metadata: dict | None = None,
    interpretation: dict | None = None,
    prescription_plan: dict | None = None,
    review_metadata: dict | None = None,
    source_medicines: list[dict] | None = None,
) -> dict:
    """
    Build the final prescription intelligence report.

    Parameters
    ----------
    safety_analysis:
        Output from analyze_prescription_safety().

    prescription_id:
        Optional prescription identifier.

    file_name:
        Original uploaded filename.

    raw_text:
        OCR-extracted prescription text.

    analysis_metadata:
        OCR and pipeline metadata.

    interpretation:
        Structured prescription interpretation.

    prescription_plan:
        Canonical prescription plan.

    Returns
    -------
    dict
        Structured report suitable for:
            - API responses
            - frontend rendering
            - PDF generation
    """

    if not isinstance(
        safety_analysis,
        dict,
    ):
        safety_analysis = {}

    if not isinstance(
        analysis_metadata,
        dict,
    ):
        analysis_metadata = {}

    if not isinstance(
        interpretation,
        dict,
    ):
        interpretation = {}

    if not isinstance(
        prescription_plan,
        dict,
    ):
        prescription_plan = {}

    if not isinstance(
        source_medicines,
        list,
    ):
        source_medicines = []

    medicines = safety_analysis.get(
        "medicines",
        [],
    )

    if not isinstance(
        medicines,
        list,
    ):
        medicines = []

    plan_medicines = prescription_plan.get(
        "medicines",
        [],
    )

    if not isinstance(
        plan_medicines,
        list,
    ):
        plan_medicines = []

    medicine_reports = []

    for index, medicine in enumerate(
        medicines
    ):

        if not isinstance(
            medicine,
            dict,
        ):
            continue

        plan_result = None

        if index < len(plan_medicines):
            candidate = plan_medicines[index]

            if isinstance(
                candidate,
                dict,
            ):
                plan_result = candidate

        # Pass the matching raw pipeline medicine so that
        # _build_medicine_report can compute the displayed
        # confidence from extraction_confidence and
        # normalization_confidence directly.
        source_med = (
            source_medicines[index]
            if index < len(source_medicines)
            and isinstance(source_medicines[index], dict)
            else None
        )

        medicine_reports.append(
            _build_medicine_report(
                medicine,
                plan_result,
                source_med,
            )
        )

    summary = _build_summary(
        safety_analysis
    )

    prescription_issues = [
        _format_issue(issue)
        for issue in safety_analysis.get(
            "prescription_issues",
            [],
        )
        if isinstance(issue, dict)
    ]

    overall_status = _determine_overall_status(
        summary
    )

    safety_status = _clean_text(
        safety_analysis.get(
            "safety_status"
        ),
        "review_required",
    )

    # -----------------------------------------------------
    # Overall intelligence confidence
    # -----------------------------------------------------

    confidence = _compute_overall_confidence(
        source_medicines
    )

    if confidence is None:
        confidence = _safe_float(
            prescription_plan.get("confidence")
        )

    if confidence is None:
        confidence = _safe_float(
            interpretation.get("confidence")
        )

    return {
        "report_version": "1.1",
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "prescription": {
            "prescription_id": prescription_id,
            "file_name": file_name,
            "raw_text": raw_text,
        },
        "overall_status": overall_status,
        "safety_status": safety_status,
        "confidence": confidence,
        "summary": summary,
        "medicines": medicine_reports,
        "prescription_issues": prescription_issues,
        "analysis_metadata": analysis_metadata,
        "interpretation": interpretation,
        "prescription_plan": prescription_plan,
        "safety_analysis": safety_analysis,
        "review": review_metadata,
    }