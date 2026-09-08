def _is_positive_number(value) -> bool:
    """
    Return True when value can be interpreted as a positive number.
    """

    if isinstance(value, bool):
        return False

    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def _is_valid_strength(value) -> bool:
    """
    Validate medicine strength.

    Supports:

        500
        2.0
        "500"
        "3 + 2"

    Combination strengths such as "3 + 2" are valid because
    they represent separate components of a combination medicine.
    """

    if value is None:
        return False

    # Numeric strength.
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value > 0

    if not isinstance(value, str):
        return False

    value = value.strip()

    if not value:
        return False

    # Simple numeric string.
    try:
        return float(value) > 0
    except ValueError:
        pass

    # Combination strength.
    #
    # Examples:
    #   "3 + 2"
    #   "3+2"
    #   "5 + 10 + 20"
    #
    # Each component must be a positive number.
    parts = value.split("+")

    if len(parts) < 2:
        return False

    for part in parts:
        part = part.strip()

        if not part:
            return False

        try:
            if float(part) <= 0:
                return False
        except ValueError:
            return False

    return True


def validate_medicines(medicines: list[dict]) -> list[dict]:
    """
    Validate extracted and normalized medicine data.

    This is a structural validation layer.

    It does NOT determine whether a medicine or dose
    is medically appropriate.

    Important:
        Combination medicine strengths such as "3 + 2 mg"
        are treated as valid structured strengths and are
        NOT mathematically combined into a single value.
    """

    findings = []

    for medicine in medicines:

        name = (
            medicine.get("generic_name")
            or medicine.get("name")
        )

        # -------------------------------------------------
        # Medicine name
        # -------------------------------------------------

        if not name:
            findings.append(
                {
                    "type": "missing_medicine_name",
                    "severity": "error",
                    "medicine": None,
                    "message": (
                        "Medicine name could not be identified."
                    ),
                }
            )
            continue

        # -------------------------------------------------
        # Extraction confidence
        # -------------------------------------------------

        extraction_confidence = medicine.get(
            "extraction_confidence"
        )

        if (
            extraction_confidence is not None
            and extraction_confidence < 0.70
        ):
            findings.append(
                {
                    "type": "low_extraction_confidence",
                    "severity": "warning",
                    "medicine": name,
                    "message": (
                        f"{name} was extracted with low confidence "
                        f"({extraction_confidence:.2f}). "
                        "Manual verification is recommended."
                    ),
                }
            )

        # -------------------------------------------------
        # Normalization confidence
        # -------------------------------------------------

        normalization_confidence = medicine.get(
            "normalization_confidence"
        )

        if (
            normalization_confidence is not None
            and normalization_confidence < 0.70
        ):
            findings.append(
                {
                    "type": "low_normalization_confidence",
                    "severity": "warning",
                    "medicine": name,
                    "message": (
                        f"{name} was normalized with low confidence "
                        f"({normalization_confidence:.2f}). "
                        "Manual verification is recommended."
                    ),
                }
            )

        # -------------------------------------------------
        # Strength validation
        # -------------------------------------------------

        strength = medicine.get(
            "strength_value"
        )

        if strength is None:
            findings.append(
                {
                    "type": "missing_strength",
                    "severity": "warning",
                    "medicine": name,
                    "message": (
                        f"{name} is missing strength information."
                    ),
                }
            )

        elif not _is_valid_strength(strength):
            findings.append(
                {
                    "type": "invalid_strength",
                    "severity": "error",
                    "medicine": name,
                    "message": (
                        f"{name} has an invalid strength value: "
                        f"{strength}."
                    ),
                }
            )

        # -------------------------------------------------
        # Dose validation
        # -------------------------------------------------

        dose = medicine.get(
            "dose_value"
        )

        if dose is None:
            findings.append(
                {
                    "type": "missing_dose",
                    "severity": "warning",
                    "medicine": name,
                    "message": (
                        f"{name} is missing dose information."
                    ),
                }
            )

        elif not _is_positive_number(dose):
            findings.append(
                {
                    "type": "invalid_dose",
                    "severity": "error",
                    "medicine": name,
                    "message": (
                        f"{name} has an invalid dose value: "
                        f"{dose}."
                    ),
                }
            )

        # -------------------------------------------------
        # Frequency validation
        # -------------------------------------------------

        frequency = medicine.get(
            "frequency_value"
        )

        if frequency is None:
            findings.append(
                {
                    "type": "missing_frequency",
                    "severity": "warning",
                    "medicine": name,
                    "message": (
                        f"{name} is missing frequency information."
                    ),
                }
            )

        elif not _is_positive_number(frequency):
            findings.append(
                {
                    "type": "invalid_frequency",
                    "severity": "error",
                    "medicine": name,
                    "message": (
                        f"{name} has an invalid frequency value: "
                        f"{frequency}."
                    ),
                }
            )

        # -------------------------------------------------
        # Daily dose validation
        # -------------------------------------------------
        #
        # Daily dose is a DERIVED value:
        #
        #     strength × dose × frequency
        #
        # If dose or frequency is already invalid, the
        # calculated daily dose is also untrustworthy.
        #
        # In that situation, report only the primary
        # validation error instead of creating a cascading
        # "invalid_daily_dose" error.
        # -------------------------------------------------

        daily_dose = medicine.get(
            "daily_dose_value"
        )

        dose_valid = (
            dose is not None
            and _is_positive_number(dose)
        )

        frequency_valid = (
            frequency is not None
            and _is_positive_number(frequency)
        )

        # -------------------------------------------------
        # Do not validate derived daily dose when its
        # inputs are missing or invalid.
        # -------------------------------------------------

        if not dose_valid or not frequency_valid:

            # The existing missing/invalid dose and frequency
            # findings above already explain the problem.
            #
            # Do not add a redundant daily-dose finding.

            continue

        # -------------------------------------------------
        # Combination medicine daily dose
        # -------------------------------------------------

        if daily_dose is None:

            daily_dose_components = medicine.get(
                "daily_dose_components"
            )

            if not daily_dose_components:

                findings.append(
                    {
                        "type": "daily_dose_not_calculated",
                        "severity": "warning",
                        "medicine": name,
                        "message": (
                            f"Daily dose could not be calculated for "
                            f"{name}."
                        ),
                    }
                )

            else:

                invalid_components = False

                for component in daily_dose_components:

                    component_value = component.get(
                        "value"
                    )

                    component_unit = component.get(
                        "unit"
                    )

                    if (
                        not _is_positive_number(
                            component_value
                        )
                        or not component_unit
                    ):
                        invalid_components = True
                        break

                if invalid_components:

                    findings.append(
                        {
                            "type": "invalid_daily_dose_components",
                            "severity": "error",
                            "medicine": name,
                            "message": (
                                f"{name} contains invalid calculated "
                                "daily dose components."
                            ),
                        }
                    )

        # -------------------------------------------------
        # Normal numeric daily dose
        # -------------------------------------------------

        elif not _is_positive_number(daily_dose):

            findings.append(
                {
                    "type": "invalid_daily_dose",
                    "severity": "error",
                    "medicine": name,
                    "message": (
                        f"{name} has an invalid calculated daily "
                        f"dose: {daily_dose}."
                    ),
                }
            )
    return findings