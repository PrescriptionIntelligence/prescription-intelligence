from backend.services.safety_checker import (
    check_drug_interactions,
)


def test_warfarin_aspirin_interaction_is_detected():
    medicines = [
        {
            "generic_name": "warfarin",
        },
        {
            "generic_name": "aspirin",
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
    assert finding["matched_drugs"] == [
        "warfarin",
        "aspirin",
    ]
    assert finding["review_action"]
    assert finding["evidence_source"]


def test_warfarin_ibuprofen_interaction_is_detected():
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


def test_interaction_aliases_are_supported():
    medicines = [
        {
            "generic_name": "Coumadin",
        },
        {
            "generic_name": "acetylsalicylic acid",
        },
    ]

    findings = check_drug_interactions(
        medicines
    )

    assert len(findings) == 1

    assert findings[0]["interaction_id"] == (
        "DDI-WARFARIN-ASPIRIN"
    )


def test_partial_interaction_is_not_flagged():
    medicines = [
        {
            "generic_name": "warfarin",
        },
    ]

    findings = check_drug_interactions(
        medicines
    )

    assert findings == []


def test_unrelated_medicines_are_not_flagged():
    medicines = [
        {
            "generic_name": "paracetamol",
        },
        {
            "generic_name": "pantoprazole",
        },
        {
            "generic_name": "amoxicillin",
        },
    ]

    findings = check_drug_interactions(
        medicines
    )

    assert findings == []


def test_interaction_matching_does_not_use_substrings():
    medicines = [
        {
            "generic_name": "notwarfarin",
        },
        {
            "generic_name": "aspirin",
        },
    ]

    findings = check_drug_interactions(
        medicines
    )

    assert findings == []


def test_simvastatin_clarithromycin_interaction():
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

    finding = findings[0]

    assert finding["interaction_id"] == (
        "DDI-SIMVASTATIN-CLARITHROMYCIN"
    )
    assert finding["severity"] == "high"
    assert finding["interaction_category"] == (
        "myopathy_risk"
    )


def test_amoxicillin_methotrexate_interaction():
    medicines = [
        {
            "generic_name": "amoxycillin",
        },
        {
            "generic_name": "methotrexate sodium",
        },
    ]

    findings = check_drug_interactions(
        medicines
    )

    assert len(findings) == 1

    finding = findings[0]

    assert finding["interaction_id"] == (
        "DDI-AMOXICILLIN-METHOTREXATE"
    )
    assert finding["severity"] == "medium"