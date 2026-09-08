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

def check_daily_dose_limits(medicines: list[dict]) -> list[dict]:
    """
    Check whether a medicine's calculated daily dose exceeds
    a configured test safety limit.

    These limits are for prototype/testing purposes only.
    They are not medical advice.
    """

    test_daily_limits = {
        "Paracetamol": 4000,
        "Cetirizine": 10,
        "Omeprazole": 40,
    }

    flags = []

    for medicine in medicines:
        medicine_name = medicine.get("generic_name") or medicine.get("name")
        daily_dose = medicine.get("daily_dose_value")
        daily_dose_unit = medicine.get("daily_dose_unit")

        if not medicine_name or daily_dose is None:
            continue

        limit = test_daily_limits.get(medicine_name)

        if limit is not None and daily_dose > limit:
            flags.append(
                {
                    "type": "daily_dose_limit_exceeded",
                    "severity": "warning",
                    "medicine": medicine_name,
                    "daily_dose": daily_dose,
                    "daily_dose_unit": daily_dose_unit,
                    "limit": limit,
                    "message": (
                        f"{medicine_name} has a calculated daily dose of "
                        f"{daily_dose} {daily_dose_unit}, which exceeds "
                        f"the configured prototype limit of {limit} "
                        f"{daily_dose_unit}."
                    ),
                }
            )

    return flags