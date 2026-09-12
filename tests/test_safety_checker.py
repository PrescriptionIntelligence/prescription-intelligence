from backend.services.safety_checker import (
    check_drug_interactions,
)


def test_warfarin_and_aspirin_interaction():
    medicines = [
        {
            "generic_name": "Warfarin",
        },
        {
            "generic_name": "Aspirin",
        },
    ]

    findings = check_drug_interactions(
        medicines
    )

    assert len(findings) == 1

    finding = findings[0]

    assert finding["type"] == "drug_interaction"
    assert finding["severity"] == "high"
    assert finding["interaction_id"] == (
        "DDI-WARFARIN-ASPIRIN"
    )
    assert finding["interaction_category"] == (
        "bleeding_risk"
    )
    assert finding["review_action"]


def test_warfarin_and_ibuprofen_interaction():
    medicines = [
        {
            "generic_name": "warfarin",
        },
        {
            "generic_name": "ibuprofen",
        },
    ]

    findings = check_drug_interactions(
        medicines
    )

    assert len(findings) == 1

    assert findings[0]["interaction_id"] == (
        "DDI-WARFARIN-IBUPROFEN"
    )


def test_simvastatin_and_clarithromycin_interaction():
    medicines = [
        {
            "generic_name": "simvastatin",
        },
        {
            "generic_name": "clarithromycin",
        },
    ]

    findings = check_drug_interactions(
        medicines
    )

    assert len(findings) == 1

    assert findings[0]["interaction_id"] == (
        "DDI-SIMVASTATIN-CLARITHROMYCIN"
    )
    assert findings[0]["severity"] == "high"


def test_amoxicillin_alias_matches_amoxicillin_interaction():
    medicines = [
        {
            "generic_name": "Amoxycillin",
        },
        {
            "generic_name": "Methotrexate",
        },
    ]

    findings = check_drug_interactions(
        medicines
    )

    assert len(findings) == 1

    assert findings[0]["interaction_id"] == (
        "DDI-AMOXICILLIN-METHOTREXATE"
    )


def test_unrelated_medicines_have_no_interaction():
    medicines = [
        {
            "generic_name": "Paracetamol",
        },
        {
            "generic_name": "Pantoprazole",
        },
    ]

    findings = check_drug_interactions(
        medicines
    )

    assert findings == []


def test_substring_does_not_create_false_positive():
    medicines = [
        {
            "generic_name": "Warfarin sodium",
        },
        {
            "generic_name": "Aspirin-like-product",
        },
    ]

    findings = check_drug_interactions(
        medicines
    )

    assert findings == []


def test_interaction_contains_evidence_metadata():
    medicines = [
        {
            "generic_name": "Warfarin",
        },
        {
            "generic_name": "Aspirin",
        },
    ]

    findings = check_drug_interactions(
        medicines
    )

    finding = findings[0]

    assert finding["matched_drugs"]
    assert finding["interaction_id"]
    assert finding["interaction_category"]
    assert finding["evidence_source"]
    assert finding["review_action"]