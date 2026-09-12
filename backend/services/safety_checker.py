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

Interaction findings are intentionally conservative and are
limited to the documented knowledge base in this module.
They must NOT be interpreted as a comprehensive interaction
database.
"""

from __future__ import annotations


# ---------------------------------------------------------
# Known drug-drug interactions
# ---------------------------------------------------------
#
# IMPORTANT:
#
# This is a curated, conservative knowledge base.
#
# It intentionally contains only drug-drug interactions.
# Drug-food, drug-alcohol and drug-supplement interactions
# should be handled by separate future safety modules.
#
# The interaction engine never recommends stopping,
# starting, or changing a medicine.
# ---------------------------------------------------------

_KNOWN_INTERACTIONS: list[dict] = [
    {
        "id": "DDI-WARFARIN-ASPIRIN",
        "drugs": ["warfarin", "aspirin"],
        "severity": "high",
        "category": "bleeding_risk",
        "message": (
            "Warfarin and Aspirin may increase bleeding risk "
            "when used together. Medical review is strongly "
            "recommended."
        ),
        "review_action": (
            "Review the combination with a doctor or pharmacist."
        ),
        "evidence_source": "FDA safety information",
    },
    {
        "id": "DDI-WARFARIN-IBUPROFEN",
        "drugs": ["warfarin", "ibuprofen"],
        "severity": "high",
        "category": "bleeding_risk",
        "message": (
            "Warfarin and Ibuprofen may increase bleeding risk "
            "when used together. Medical review is strongly "
            "recommended."
        ),
        "review_action": (
            "Review the combination with a doctor or pharmacist."
        ),
        "evidence_source": "FDA drug safety information",
    },
    {
        "id": "DDI-WARFARIN-NAPROXEN",
        "drugs": ["warfarin", "naproxen"],
        "severity": "high",
        "category": "bleeding_risk",
        "message": (
            "Warfarin and Naproxen may increase bleeding risk "
            "when used together. Medical review is strongly "
            "recommended."
        ),
        "review_action": (
            "Review the combination with a doctor or pharmacist."
        ),
        "evidence_source": "FDA drug interaction information",
    },
    {
        "id": "DDI-SIMVASTATIN-CLARITHROMYCIN",
        "drugs": ["simvastatin", "clarithromycin"],
        "severity": "high",
        "category": "myopathy_risk",
        "message": (
            "Simvastatin and Clarithromycin may substantially "
            "increase the risk of muscle toxicity, including "
            "myopathy and rhabdomyolysis."
        ),
        "review_action": (
            "Review the combination with a doctor or pharmacist."
        ),
        "evidence_source": "FDA prescribing information",
    },
    {
        "id": "DDI-SIMVASTATIN-ERYTHROMYCIN",
        "drugs": ["simvastatin", "erythromycin"],
        "severity": "high",
        "category": "myopathy_risk",
        "message": (
            "Simvastatin and Erythromycin may increase the risk "
            "of muscle toxicity, including myopathy and "
            "rhabdomyolysis."
        ),
        "review_action": (
            "Review the combination with a doctor or pharmacist."
        ),
        "evidence_source": "FDA prescribing information",
    },
    {
        "id": "DDI-AMOXICILLIN-METHOTREXATE",
        "drugs": ["amoxicillin", "methotrexate"],
        "severity": "medium",
        "category": "toxicity_risk",
        "message": (
            "Amoxicillin and Methotrexate may interact and "
            "increase the risk of methotrexate-related toxicity."
        ),
        "review_action": (
            "Review the combination with a doctor or pharmacist."
        ),
        "evidence_source": "Drug interaction reference",
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
# Medicine aliases
# ---------------------------------------------------------
#
# Aliases are used only for interaction matching.
# They do not change the medicine identity stored by
# the prescription pipeline.
# ---------------------------------------------------------

_MEDICINE_ALIASES: dict[str, set[str]] = {
    "warfarin": {
        "warfarin",
        "coumadin",
    },
    "aspirin": {
        "aspirin",
        "acetylsalicylic acid",
    },
    "ibuprofen": {
        "ibuprofen",
    },
    "naproxen": {
        "naproxen",
    },
    "simvastatin": {
        "simvastatin",
    },
    "clarithromycin": {
        "clarithromycin",
    },
    "erythromycin": {
        "erythromycin",
    },
    "amoxicillin": {
        "amoxicillin",
        "amoxycillin",
    },
    "methotrexate": {
        "methotrexate",
        "methotrexate sodium",
    },
}


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------


def _normalize_for_interaction(
    name: str,
) -> str:
    """
    Normalize a medicine name for interaction lookup.
    """

    if not name:
        return ""

    normalized = (
        str(name)
        .strip()
        .lower()
    )

    # Collapse repeated whitespace.
    normalized = " ".join(
        normalized.split()
    )

    return normalized


def _medicine_matches_canonical(
    medicine_name: str,
    canonical_name: str,
) -> bool:
    """
    Determine whether a medicine name represents the
    requested canonical medicine.

    Matching is alias-based rather than arbitrary substring
    matching to reduce false-positive interactions.
    """

    normalized_name = (
        _normalize_for_interaction(
            medicine_name
        )
    )

    if not normalized_name:
        return False

    aliases = _MEDICINE_ALIASES.get(
        canonical_name,
        {canonical_name},
    )

    return normalized_name in aliases


def _find_matching_medicines(
    medicines: list[dict],
    canonical_name: str,
) -> list[str]:
    """
    Return display names of medicines matching a canonical
    interaction ingredient.
    """

    matches = []

    for medicine in medicines:

        medicine_name = (
            medicine.get("generic_name")
            or medicine.get("name")
            or medicine.get(
                "normalized_name"
            )
        )

        if not medicine_name:
            continue

        if _medicine_matches_canonical(
            medicine_name,
            canonical_name,
        ):
            matches.append(
                str(medicine_name)
            )

    return matches


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
            or medicine.get(
                "normalized_name"
            )
        )

        if not name:
            continue

        normalized_name = (
            _normalize_for_interaction(
                name
            )
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

    This function is intentionally conservative.

    It:
        - checks only drug-drug interactions
        - uses canonical names and explicit aliases
        - avoids arbitrary substring matching
        - returns structured findings
        - never recommends changing therapy

    It does NOT:
        - claim comprehensive interaction coverage
        - diagnose the patient
        - recommend stopping medication
        - recommend changing dosage
    """

    flags = []

    for interaction in _KNOWN_INTERACTIONS:

        interacting_drugs = interaction[
            "drugs"
        ]

        matched_display_names = []

        all_drugs_matched = True

        for canonical_name in interacting_drugs:

            matches = _find_matching_medicines(
                medicines,
                canonical_name,
            )

            if not matches:
                all_drugs_matched = False
                break

            matched_display_names.extend(
                matches
            )

        if not all_drugs_matched:
            continue

        # Remove duplicates while preserving order.
        unique_display_names = list(
            dict.fromkeys(
                matched_display_names
            )
        )

        flags.append(
            {
                "type": "drug_interaction",
                "severity": interaction[
                    "severity"
                ],
                "medicine": " + ".join(
                    unique_display_names
                ),
                "matched_drugs": list(
                    interacting_drugs
                ),
                "interaction_id": interaction[
                    "id"
                ],
                "interaction_category": interaction[
                    "category"
                ],
                "message": interaction[
                    "message"
                ],
                "review_action": interaction[
                    "review_action"
                ],
                "evidence_source": interaction[
                    "evidence_source"
                ],
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

    An explicit strength conflict is handled separately by the
    clinical safety layer and should not also be reported as a
    generic medicine-identification ambiguity.
    """

    flags = []

    review_threshold = 0.70

    for medicine in medicines:

        name = (
            medicine.get("generic_name")
            or medicine.get("name")
            or medicine.get(
                "normalized_name"
            )
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

        resolution = medicine.get("resolution")

        if not isinstance(resolution, dict):
            resolution = {}

        resolution_reason = (
            medicine.get("resolution_reason")
            or resolution.get("reason")
            or ""
        )

        resolution_status = (
            medicine.get("resolution_status")
            or resolution.get("status")
            or ""
        )

        # -----------------------------------------------------
        # Explicit strength conflicts are handled by the
        # clinical safety layer as a high-severity finding.
        # Do not also downgrade the same medicine to a generic
        # medium-severity identity ambiguity.
        # -----------------------------------------------------

        strength_conflict = (
            resolution_reason == "strength_conflict"
            or str(resolution_reason).startswith(
                "strength_conflict:"
            )
            or medicine.get("strength_verification") == "strength_conflict"
            or str(
                medicine.get("strength_verification") or ""
            ).startswith("strength_conflict:")
        )

        if strength_conflict:
            continue

        if (
            needs_review
            or status in (
                "UNKNOWN",
                "REVIEW REQUIRED",
            )
            or resolution_status in (
                "needs_review",
                "review_required",
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
                        f"{name} has low identification confidence. "
                        "Manual verification is recommended before "
                        "dispensing."
                    ),
                }
            )

    return flags

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
            or medicine.get(
                "normalized_name"
            )
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
            _normalize_for_interaction(
                medicine_name
            )
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
