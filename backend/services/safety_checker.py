"""
Safety Checker

Performs conservative prescription-level safety checks
using structured information produced by the extraction
and normalization pipeline.

This module is a decision-support layer.

It does NOT:
    - diagnose
    - prescribe
    - confirm uncertain medicines
    - replace pharmacist/doctor review
    - make unsupported clinical claims

Severity contract:
    high
    medium
    low

All safety findings returned by this module follow the
same severity vocabulary used by the report layer.
"""

from __future__ import annotations


# ---------------------------------------------------------
# Known drug-drug interactions
# ---------------------------------------------------------
#
# This is intentionally a small, conservative knowledge base.
#
# It must NOT be interpreted as a comprehensive interaction
# database.
#
# Only documented interaction pairs should be added.
# ---------------------------------------------------------

_KNOWN_INTERACTIONS: list[dict] = [
    {
        "drugs": {"warfarin", "aspirin"},
        "severity": "high",
        "message": (
            "Warfarin and Aspirin may increase bleeding risk when "
            "used together. Medical review is strongly recommended."
        ),
    },
    {
        "drugs": {"warfarin", "ibuprofen"},
        "severity": "high",
        "message": (
            "Warfarin and Ibuprofen may increase bleeding risk. "
            "Medical review is strongly recommended."
        ),
    },
    {
        "drugs": {"metformin", "alcohol"},
        "severity": "medium",
        "message": (
            "Metformin combined with alcohol may increase the risk "
            "of lactic acidosis. Medical review is recommended."
        ),
    },
    {
        "drugs": {"simvastatin", "clarithromycin"},
        "severity": "high",
        "message": (
            "Simvastatin and Clarithromycin combination may increase "
            "the risk of muscle toxicity (myopathy/rhabdomyolysis)."
        ),
    },
    {
        "drugs": {"methotrexate", "nsaids"},
        "severity": "high",
        "message": (
            "Methotrexate and NSAIDs (e.g. ibuprofen) may increase "
            "methotrexate toxicity risk."
        ),
    },
    {
        "drugs": {"lisinopril", "potassium"},
        "severity": "medium",
        "message": (
            "ACE inhibitors (e.g. Lisinopril) combined with potassium "
            "supplements may cause hyperkalemia. Review recommended."
        ),
    },
    {
        "drugs": {"ciprofloxacin", "antacids"},
        "severity": "medium",
        "message": (
            "Ciprofloxacin absorption is reduced by antacids. "
            "Separate dosing times by at least 2 hours."
        ),
    },
    {
        "drugs": {"amoxicillin", "methotrexate"},
        "severity": "medium",
        "message": (
            "Amoxicillin may increase methotrexate plasma levels. "
            "Monitor for signs of toxicity."
        ),
    },
]


# ---------------------------------------------------------
# Daily-dose reference limits
# ---------------------------------------------------------
#
# These are limited reference checks, not comprehensive
# dosing guidance.
# ---------------------------------------------------------

_DAILY_DOSE_LIMITS: dict[str, tuple[float, str]] = {
    "paracetamol": (4000.0, "4000 mg"),
    "acetaminophen": (4000.0, "4000 mg"),
    "ibuprofen": (2400.0, "2400 mg (OTC)"),
    "cetirizine": (10.0, "10 mg"),
    "omeprazole": (40.0, "40 mg"),
    "amoxicillin": (3000.0, "3000 mg"),
    "metformin": (3000.0, "3000 mg"),
}


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------


def _normalize_for_interaction(name: str) -> str:
    """
    Normalize a medicine name for interaction lookup.
    """

    return name.strip().lower()


# ---------------------------------------------------------
# Duplicate medicine check
# ---------------------------------------------------------


def check_duplicate_medicines(
    medicines: list[dict],
) -> list[dict]:
    """
    Detect duplicate medicines in a prescription.

    Medicines should already be normalized before reaching
    this function.
    """

    findings = []
    seen: set[str] = set()

    for medicine in medicines:

        name = (
            medicine.get("generic_name")
            or medicine.get("name")
        )

        if not name:
            continue

        normalized_name = (
            name.strip().lower()
        )

        if normalized_name in seen:

            findings.append(
                {
                    "type": "duplicate_medicine",
                    "severity": "medium",
                    "medicine": name,
                    "message": (
                        f"{name} appears more than once "
                        "in the prescription."
                    ),
                }
            )

        else:
            seen.add(
                normalized_name
            )

    return findings


# ---------------------------------------------------------
# Drug interaction check
# ---------------------------------------------------------


def check_drug_interactions(
    medicines: list[dict],
) -> list[dict]:
    """
    Check for known documented drug-drug interactions.

    This is intentionally conservative and limited to the
    interaction pairs defined in _KNOWN_INTERACTIONS.

    It must never be interpreted as a comprehensive
    interaction database.
    """

    flags = []

    present_names = {
        _normalize_for_interaction(
            medicine.get("generic_name")
            or medicine.get("name")
            or ""
        )
        for medicine in medicines
        if (
            medicine.get("generic_name")
            or medicine.get("name")
        )
    }

    for interaction in _KNOWN_INTERACTIONS:

        interacting_drugs = interaction["drugs"]

        matched = set()

        for drug in interacting_drugs:

            for name in present_names:

                if (
                    drug in name
                    or name in drug
                ):
                    matched.add(drug)
                    break

        if matched != interacting_drugs:
            continue

        display_names = []

        for medicine in medicines:

            medicine_name = (
                medicine.get("generic_name")
                or medicine.get("name")
                or ""
            )

            normalized_name = (
                _normalize_for_interaction(
                    medicine_name
                )
            )

            for drug in interacting_drugs:

                if (
                    drug in normalized_name
                    or normalized_name in drug
                ):
                    display_names.append(
                        medicine_name
                    )
                    break

        flags.append(
            {
                "type": "drug_interaction",
                "severity": interaction["severity"],
                "medicine": " + ".join(
                    display_names
                ),
                "message": interaction["message"],
            }
        )

    return flags


# ---------------------------------------------------------
# Ambiguous medicine check
# ---------------------------------------------------------


def check_ambiguous_medicines(
    medicines: list[dict],
) -> list[dict]:
    """
    Flag medicines that could not be reliably identified.

    A medicine is considered ambiguous if:
      - needs_review is True
      - status is UNKNOWN / REVIEW REQUIRED
      - normalization confidence is below 0.70
    """

    flags = []

    review_threshold = 0.70

    for medicine in medicines:

        name = (
            medicine.get("generic_name")
            or medicine.get("name")
        )

        if not name:
            continue

        normalization_confidence = medicine.get(
            "normalization_confidence"
        )

        needs_review = medicine.get(
            "needs_review"
        )

        status = (
            medicine.get("status")
            or ""
        ).upper()

        if (
            needs_review
            or status in (
                "UNKNOWN",
                "REVIEW REQUIRED",
            )
        ):

            flags.append(
                {
                    "type": "ambiguous_medicine",
                    "severity": "medium",
                    "medicine": name,
                    "message": (
                        f"{name} could not be reliably identified. "
                        "Manual verification is required before "
                        "dispensing."
                    ),
                }
            )

        elif (
            normalization_confidence is not None
            and normalization_confidence
            < review_threshold
        ):

            flags.append(
                {
                    "type": "low_identification_confidence",
                    "severity": "medium",
                    "medicine": name,
                    "message": (
                        f"{name} was identified with low confidence "
                        f"({normalization_confidence:.0%}). "
                        "Please verify the medicine name before "
                        "dispensing."
                    ),
                }
            )

    return flags


# ---------------------------------------------------------
# Daily-dose limit check
# ---------------------------------------------------------


def check_daily_dose_limits(
    medicines: list[dict],
) -> list[dict]:
    """
    Check whether a calculated daily dose exceeds a limited
    documented reference threshold.

    These checks are informational safety checks only.

    They are NOT:
        - personalized dosing recommendations
        - comprehensive dosing validation
        - medical advice

    Combination medicines are skipped here when their daily
    dose is represented as separate components because those
    components may represent different active ingredients.
    """

    flags = []

    for medicine in medicines:

        medicine_name = (
            medicine.get("generic_name")
            or medicine.get("name")
        )

        daily_dose = medicine.get(
            "daily_dose_value"
        )

        daily_dose_unit = medicine.get(
            "daily_dose_unit"
        )

        if (
            not medicine_name
            or daily_dose is None
        ):
            continue

        name_lower = (
            medicine_name.strip().lower()
        )

        limit_entry = _DAILY_DOSE_LIMITS.get(
            name_lower
        )

        if limit_entry is None:
            continue

        limit_value, limit_display = (
            limit_entry
        )

        try:
            daily_dose_numeric = float(
                daily_dose
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

        if daily_dose_numeric <= limit_value:
            continue

        flags.append(
            {
                "type": "daily_dose_limit_exceeded",
                "severity": "high",
                "medicine": medicine_name,
                "daily_dose": daily_dose_numeric,
                "daily_dose_unit": daily_dose_unit,
                "limit": limit_value,
                "message": (
                    f"{medicine_name} has a calculated daily dose "
                    f"of {daily_dose_numeric} "
                    f"{daily_dose_unit or 'mg'}, which exceeds "
                    f"the standard reference limit of "
                    f"{limit_display}. This requires medical "
                    "review before dispensing."
                ),
            }
        )

    return flags