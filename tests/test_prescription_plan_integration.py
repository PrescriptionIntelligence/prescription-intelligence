from backend.services.prescription_pipeline import process_prescription


SAMPLE_PRESCRIPTION = (
    "Amoxicillin 500 mg, 1 tablet twice daily for 5 days"
)


def test_pipeline_preserves_structured_prescription_fields():
    result = process_prescription(SAMPLE_PRESCRIPTION)

    assert result["medicines"]

    medicine = result["medicines"][0]

    assert medicine["generic_name"] == "Amoxicillin"
    assert medicine["strength_value"] == 500.0
    assert medicine["strength_unit"] == "mg"
    assert medicine["dose_value"] == 1.0
    assert medicine["dose_unit"] == "tablet"
    assert medicine["route"] == "oral"
    assert medicine["frequency_value"] == 2
    assert medicine["frequency_unit"] == "daily"
    assert medicine["duration_value"] == 5.0
    assert medicine["duration_unit"] == "days"


def test_interpretation_preserves_structured_fields():
    result = process_prescription(SAMPLE_PRESCRIPTION)

    interpreted = result["interpretation"]["medicines"][0]

    assert interpreted["strength_value"] == 500.0
    assert interpreted["strength_unit"] == "mg"
    assert interpreted["dose_value"] == 1.0
    assert interpreted["dose_unit"] == "tablet"
    assert interpreted["route"] == "oral"
    assert interpreted["frequency_value"] == 2
    assert interpreted["frequency_unit"] == "daily"
    assert interpreted["duration_value"] == 5.0
    assert interpreted["duration_unit"] == "days"


def test_resolved_plan_does_not_create_instruction_uncertainty():
    result = process_prescription(SAMPLE_PRESCRIPTION)

    plan = result["prescription_plan"]

    assert plan["status"] == "resolved"
    assert plan["review_required_count"] == 0

    medicine_plan = plan["medicines"][0]

    assert medicine_plan["needs_review"] is False
    assert medicine_plan["review_reasons"]["medicine"] is False
    assert medicine_plan["review_reasons"]["instructions"] is False


def test_clean_prescription_has_no_structural_safety_issues():
    result = process_prescription(SAMPLE_PRESCRIPTION)

    safety_analysis = result["safety_analysis"]

    assert safety_analysis["safety_status"] == (
        "no_structural_issues_detected"
    )
    assert safety_analysis["issue_count"] == 0
    assert safety_analysis["high_severity_count"] == 0
    assert safety_analysis["medium_severity_count"] == 0
    assert safety_analysis["low_severity_count"] == 0
    assert safety_analysis["prescription_issues"] == []

    assert result["safety_flags"] == []


def test_pipeline_safety_metadata_uses_safety_status():
    result = process_prescription(SAMPLE_PRESCRIPTION)

    assert result["analysis_metadata"]["needs_review"] is False
    assert result["analysis_metadata"]["safety_analysis_status"] == (
        "no_structural_issues_detected"
    )


def test_explicit_tablet_instruction_is_preserved_in_plan():
    result = process_prescription(SAMPLE_PRESCRIPTION)

    medicine_plan = result["prescription_plan"]["medicines"][0]

    assert medicine_plan["medicine"]["dosage_form"] == "Tablet"
    assert medicine_plan["instructions"]["quantity"] == 1.0
    assert medicine_plan["instructions"]["frequency"] == "twice_daily"
    assert medicine_plan["instructions"]["duration"]["value"] == 5.0
    assert medicine_plan["instructions"]["route"] == "oral"

def test_explicit_prescription_strength_overrides_resolved_strength():
    result = process_prescription(
        "Paracetamol 650 mg, 1 tablet three times daily for 3 days"
    )

    medicine = result["medicines"][0]
    medicine_plan = result["prescription_plan"]["medicines"][0]

    assert medicine["strength_value"] == 650.0
    assert medicine["strength_unit"] == "mg"

    assert medicine_plan["medicine"]["strength_value"] == 650.0
    assert medicine_plan["medicine"]["strength_unit"] == "mg"