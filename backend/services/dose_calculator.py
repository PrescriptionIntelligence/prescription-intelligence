def calculate_daily_dose(medicine: dict) -> dict:
    """
    Calculate the total daily dose of a medicine.

    Normal medicine:
        strength × dose × frequency

    Example:
        500 mg × 1 tablet × 2/day
        = 1000 mg/day

    Combination strength:
        3 + 2 mg

    Each component is calculated independently.
    The components are NEVER combined into 5 mg.
    """

    strength = medicine.get("strength_value")
    dose = medicine.get("dose_value")
    frequency = medicine.get("frequency_value")

    # -----------------------------------------------------
    # Required information is missing.
    # -----------------------------------------------------

    if (
        strength is None
        or dose is None
        or frequency is None
    ):
        return {
            **medicine,
            "daily_dose_value": None,
            "daily_dose_unit": None,
            "daily_dose_components": [],
        }

    # -----------------------------------------------------
    # Validate dose and frequency.
    # -----------------------------------------------------

    if not isinstance(dose, (int, float)):
        return {
            **medicine,
            "daily_dose_value": None,
            "daily_dose_unit": None,
            "daily_dose_components": [],
        }

    if not isinstance(frequency, (int, float)):
        return {
            **medicine,
            "daily_dose_value": None,
            "daily_dose_unit": None,
            "daily_dose_components": [],
        }

    # -----------------------------------------------------
    # Combination strength.
    #
    # Example:
    #   strength_value = "3+2"
    #
    #   strength_components = [
    #       {"value": 3, "unit": "mg"},
    #       {"value": 2, "unit": "mg"}
    #   ]
    # -----------------------------------------------------

    if isinstance(strength, str):

        strength_components = medicine.get(
            "strength_components",
            [],
        )

        if not strength_components:
            return {
                **medicine,
                "daily_dose_value": None,
                "daily_dose_unit": None,
                "daily_dose_components": [],
            }

        daily_dose_components = []

        for component in strength_components:

            if not isinstance(component, dict):
                continue

            component_value = component.get("value")
            component_unit = component.get("unit")

            if not isinstance(
                component_value,
                (int, float),
            ):
                continue

            daily_value = (
                component_value
                * dose
                * frequency
            )

            daily_dose_components.append(
                {
                    "value": daily_value,
                    "unit": component_unit,
                }
            )

        if not daily_dose_components:
            return {
                **medicine,
                "daily_dose_value": None,
                "daily_dose_unit": None,
                "daily_dose_components": [],
            }

        return {
            **medicine,
            "daily_dose_value": None,
            "daily_dose_unit": None,
            "daily_dose_components": (
                daily_dose_components
            ),
        }

    # -----------------------------------------------------
    # Normal single numeric strength.
    # -----------------------------------------------------

    if not isinstance(
        strength,
        (int, float),
    ):
        return {
            **medicine,
            "daily_dose_value": None,
            "daily_dose_unit": None,
            "daily_dose_components": [],
        }

    daily_dose = (
        strength
        * dose
        * frequency
    )

    return {
        **medicine,
        "daily_dose_value": daily_dose,
        "daily_dose_unit": medicine.get(
            "strength_unit"
        ),
        "daily_dose_components": [],
    }


def calculate_daily_doses(
    medicines: list[dict],
) -> list[dict]:
    """
    Calculate daily dose for every medicine
    in a prescription.
    """

    return [
        calculate_daily_dose(medicine)
        for medicine in medicines
    ]