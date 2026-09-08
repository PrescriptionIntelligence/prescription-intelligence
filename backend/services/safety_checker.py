# Known drug-drug interactions for safety checks.
# These are documented, publicly known interaction pairs.
# This list is intentionally conservative and limited.
# DO NOT add speculative interactions.
# Severity:
#   "high"    = potentially serious, requires immediate attention
#   "warning" = caution warranted, review recommended
#   "info"    = informational, low clinical impact

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
        "severity": "warning",
        "message": (
            "Metformin combined with alcohol may increase the risk "
            "of lactic acidosis."
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
        "severity": "warning",
        "message": (
            "ACE inhibitors (e.g. Lisinopril) combined with potassium "
            "supplements may cause hyperkalemia. Review recommended."
        ),
    },
    {
        "drugs": {"ciprofloxacin", "antacids"},
        "severity": "warning",
        "message": (
            "Ciprofloxacin absorption is reduced by antacids. "
            "Separate dosing times by at least 2 hours."
        ),
    },
    {
        "drugs": {"amoxicillin", "methotrexate"},
        "severity": "warning",
        "message": (
            "Amoxicillin may increase methotrexate plasma levels. "
            "Monitor for signs of toxicity."
        ),
    },
]


def _normalize_for_interaction(name: str) -> str:
    """
    Normalize a medicine name for interaction lookup.
    """
    return name.strip().lower()


def check_duplicate_medicines(medicines: list[dict]) -> list[dict]:
    """
    Detect duplicate medicines in a prescription.

    Medicines should already be normalized before reaching this function.
    """

    findings = []
    seen = {}

    for medicine in medicines:
        name = medicine.get("generic_name") or medicine.get("name")

        if not name:
            continue

        normalized_name = name.strip().lower()

        if normalized_name in seen:
            findings.append(
                {
                    "type": "duplicate_medicine",
                    "severity": "warning",
                    "medicine": name,
                    "message": (
                        f"{name} appears more than once in the prescription."
                    ),
                }
            )
        else:
            seen[normalized_name] = medicine

    return findings


def check_drug_interactions(medicines: list[dict]) -> list[dict]:
    """
    Check for known documented drug-drug interactions.

    Only uses a conservative, known interaction list.
    Never fabricates interactions.
    """

    flags = []

    # Build a set of normalized names present in the prescription.
    present_names = {
        _normalize_for_interaction(
            m.get("generic_name") or m.get("name") or ""
        )
        for m in medicines
        if m.get("generic_name") or m.get("name")
    }

    for interaction in _KNOWN_INTERACTIONS:
        interacting_drugs = interaction["drugs"]

        # Check if both drugs in the interaction pair are present.
        # Use subset matching so partial names can still match.
        matched = set()
        for drug in interacting_drugs:
            for name in present_names:
                if drug in name or name in drug:
                    matched.add(drug)
                    break

        if matched == interacting_drugs:
            # Find the display names from actual medicines
            display_names = []
            for m in medicines:
                mname = _normalize_for_interaction(
                    m.get("generic_name") or m.get("name") or ""
                )
                for drug in interacting_drugs:
                    if drug in mname or mname in drug:
                        display_names.append(
                            m.get("generic_name") or m.get("name")
                        )
                        break

            flags.append(
                {
                    "type": "drug_interaction",
                    "severity": interaction["severity"],
                    "medicine": " + ".join(display_names),
                    "message": interaction["message"],
                }
            )

    return flags


def check_ambiguous_medicines(medicines: list[dict]) -> list[dict]:
    """
    Flag medicines that could not be reliably identified.

    A medicine is considered ambiguous if:
      - normalization_confidence is below the review threshold
      - needs_review is explicitly True
      - medicine status is UNKNOWN or REVIEW REQUIRED
    """

    flags = []
    REVIEW_THRESHOLD = 0.70

    for medicine in medicines:
        name = medicine.get("generic_name") or medicine.get("name")

        if not name:
            continue

        norm_confidence = medicine.get("normalization_confidence")
        needs_review = medicine.get("needs_review")
        status = (medicine.get("status") or "").upper()

        if needs_review or status in ("UNKNOWN", "REVIEW REQUIRED"):
            flags.append(
                {
                    "type": "ambiguous_medicine",
                    "severity": "warning",
                    "medicine": name,
                    "message": (
                        f"{name} could not be reliably identified. "
                        "Manual verification is required before dispensing."
                    ),
                }
            )
        elif (
            norm_confidence is not None
            and norm_confidence < REVIEW_THRESHOLD
        ):
            flags.append(
                {
                    "type": "low_identification_confidence",
                    "severity": "warning",
                    "medicine": name,
                    "message": (
                        f"{name} was identified with low confidence "
                        f"({norm_confidence:.0%}). "
                        "Please verify the medicine name before dispensing."
                    ),
                }
            )

    return flags


def check_daily_dose_limits(medicines: list[dict]) -> list[dict]:
    """
    Check whether a medicine's calculated daily dose exceeds
    a documented safety limit.

    These limits are based on commonly referenced maximum adult
    daily doses. They are NOT medical advice.
    They are informational safety checks only.

    Sources referenced:
      - Paracetamol: 4000 mg/day (UK BNF, FDA)
      - Ibuprofen: 2400 mg/day (OTC), 3200 mg/day (prescription max)
      - Cetirizine: 10 mg/day
      - Omeprazole: 40 mg/day (standard), 80 mg/day (maximum)
      - Amoxicillin: 3000 mg/day (standard), 6000 mg/day (high-dose)
      - Metformin: 3000 mg/day
    """

    # medicine_name_lower -> (limit_mg, display_limit)
    daily_limits: dict[str, tuple[float, str]] = {
        "paracetamol": (4000.0, "4000 mg"),
        "acetaminophen": (4000.0, "4000 mg"),
        "ibuprofen": (2400.0, "2400 mg (OTC)"),
        "cetirizine": (10.0, "10 mg"),
        "omeprazole": (40.0, "40 mg"),
        "amoxicillin": (3000.0, "3000 mg"),
        "metformin": (3000.0, "3000 mg"),
    }

    flags = []

    for medicine in medicines:
        medicine_name = medicine.get("generic_name") or medicine.get("name")
        daily_dose = medicine.get("daily_dose_value")
        daily_dose_unit = medicine.get("daily_dose_unit")

        if not medicine_name or daily_dose is None:
            continue

        name_lower = medicine_name.strip().lower()
        limit_entry = daily_limits.get(name_lower)

        if limit_entry is None:
            continue

        limit_value, limit_display = limit_entry

        if daily_dose > limit_value:
            flags.append(
                {
                    "type": "daily_dose_limit_exceeded",
                    "severity": "high",
                    "medicine": medicine_name,
                    "daily_dose": daily_dose,
                    "daily_dose_unit": daily_dose_unit,
                    "limit": limit_value,
                    "message": (
                        f"{medicine_name} has a calculated daily dose of "
                        f"{daily_dose} {daily_dose_unit or 'mg'}, which exceeds "
                        f"the standard reference limit of {limit_display}. "
                        "This requires medical review before dispensing."
                    ),
                }
            )

    return flags
