from backend.services.prescription_parser import extract_medicines
from backend.services.dose_calculator import calculate_daily_doses
from backend.services.prescription_validator import validate_medicines
from backend.services.safety_checker import (
    check_daily_dose_limits,
    check_duplicate_medicines,
)


def process_prescription(raw_text: str) -> dict:
    """
    Run the complete prescription intelligence pipeline.

    OCR text
        ↓
    Medicine extraction
        ↓
    OCR/extraction quality check
        ↓
    Daily dose calculation
        ↓
    Structural validation
        ↓
    Safety checks
    """

    # 1. Extract medicines
    medicines = extract_medicines(raw_text)
    
    # 2. Calculate daily doses
    medicines = calculate_daily_doses(medicines)

    # 3. Validate extracted data
    validation_flags = validate_medicines(medicines)

    # 4. Run safety checks
    safety_flags = []

    # If OCR produced text but no medicines could be extracted,
    # do not treat this as "no safety issues".
    if raw_text.strip() and not medicines:
        safety_flags.append(
            {
                "type": "ocr_extraction_failed",
                "severity": "warning",
                "medicine": None,
                "message": (
                    "No medicines could be reliably extracted from "
                    "the prescription. Please upload a clearer image "
                    "or verify the prescription manually."
                ),
            }
        )

    # Structural validation
    safety_flags.extend(
        validation_flags
    )

    # Duplicate medicine check
    safety_flags.extend(
        check_duplicate_medicines(medicines)
    )

    # Daily dose limit check
    safety_flags.extend(
        check_daily_dose_limits(medicines)
    )

    return {
        "medicines": medicines,
        "safety_flags": safety_flags,
    }