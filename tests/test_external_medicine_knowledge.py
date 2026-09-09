from unittest.mock import patch

from backend.services.external_medicine_knowledge import (
    _derive_external_confidence,
    _extract_approximate_matches,
    _normalize_match_text,
    _safe_float,
    lookup_external_medicine,
    lookup_rxnorm,
)


def test_safe_float_handles_valid_and_invalid_values():
    assert _safe_float("12.5") == 12.5
    assert _safe_float(7) == 7.0
    assert _safe_float(None) == 0.0
    assert _safe_float("not-a-number") == 0.0


def test_normalize_match_text():
    assert (
        _normalize_match_text("Azithromycin 500-mg")
        == "azithromycin 500 mg"
    )

    assert (
        _normalize_match_text("Amoxicillin 500 / mg")
        == "amoxicillin 500 / mg"
    )

    assert (
        _normalize_match_text("  PARACETAMOL   500 mg  ")
        == "paracetamol 500 mg"
    )


def test_extract_approximate_matches():
    payload = {
        "approximateGroup": {
            "candidate": [
                {
                    "rxcui": "12345",
                    "score": "12.78",
                    "rank": "1",
                    "name": "Azithromycin 500 MG Oral Tablet",
                    "source": "RxNorm",
                }
            ]
        }
    }

    result = _extract_approximate_matches(payload)

    assert len(result) == 1
    assert result[0]["rxcui"] == "12345"
    assert result[0]["score"] == 12.78
    assert result[0]["rank"] == 1
    assert result[0]["name"] == "Azithromycin 500 MG Oral Tablet"
    assert result[0]["source"] == "RxNorm"


def test_extract_approximate_matches_handles_empty_payload():
    assert _extract_approximate_matches(None) == []
    assert _extract_approximate_matches({}) == []


def test_extract_approximate_matches_handles_single_candidate_dict():
    payload = {
        "approximateGroup": {
            "candidate": {
                "rxcui": "12345",
                "score": "10",
                "rank": "1",
            }
        }
    }

    result = _extract_approximate_matches(payload)

    assert len(result) == 1
    assert result[0]["rxcui"] == "12345"


def test_extract_approximate_matches_skips_invalid_candidates():
    payload = {
        "approximateGroup": {
            "candidate": [
                {},
                {"name": "Missing RxCUI"},
                "invalid",
                {
                    "rxcui": "67890",
                    "score": "5",
                    "rank": "2",
                },
            ]
        }
    }

    result = _extract_approximate_matches(payload)

    assert len(result) == 1
    assert result[0]["rxcui"] == "67890"


def test_derive_external_confidence_is_conservative():
    confidence = _derive_external_confidence(
        rank="1",
        raw_score=20,
        candidate_count=1,
    )

    assert confidence > 0.50
    assert confidence <= 0.74
    assert confidence < 0.78


def test_derive_external_confidence_does_not_treat_rxnorm_score_as_percentage():
    confidence = _derive_external_confidence(
        rank="1",
        raw_score=12.788553237915039,
        candidate_count=1,
    )

    assert confidence > 0.50
    assert confidence < 0.78


def test_derive_external_confidence_multiple_candidates_is_bounded():
    confidence = _derive_external_confidence(
        rank="1",
        raw_score=20,
        candidate_count=4,
    )

    assert 0.0 <= confidence <= 0.74


def test_derive_external_confidence_lower_rank_is_bounded():
    confidence = _derive_external_confidence(
        rank="3",
        raw_score=10,
        candidate_count=1,
    )

    assert 0.0 <= confidence <= 0.74


def test_lookup_rxnorm_empty_text_returns_empty():
    assert lookup_rxnorm("") == []
    assert lookup_rxnorm("   ") == []


def test_lookup_rxnorm_non_positive_top_k_returns_empty():
    assert lookup_rxnorm("paracetamol", top_k=0) == []
    assert lookup_rxnorm("paracetamol", top_k=-1) == []


def test_lookup_rxnorm_returns_normalized_external_hypothesis():
    payload = {
        "approximateGroup": {
            "candidate": [
                {
                    "rxcui": "161",
                    "score": "25.0",
                    "rank": "1",
                    "name": "Acetaminophen 500 MG Oral Tablet",
                    "source": "RxNorm",
                }
            ]
        }
    }

    with patch(
        "backend.services.external_medicine_knowledge._http_get_json",
        return_value=payload,
    ):
        result = lookup_rxnorm("paracetamol")

    assert len(result) == 1

    medicine = result[0]

    assert medicine["normalized_name"] == (
        "Acetaminophen 500 MG Oral Tablet"
    )
    assert medicine["generic_name"] == (
        "Acetaminophen 500 MG Oral Tablet"
    )
    assert medicine["matched_term"] == "paracetamol"
    assert medicine["rxcui"] == "161"
    assert medicine["raw_rxnorm_score"] == 25.0
    assert medicine["rank"] == 1
    assert medicine["source"] == "RxNorm"
    assert medicine["source_id"] == "161"
    assert medicine["match_method"] == "approximate_term"
    assert medicine["source_confidence"] <= 0.74
    assert medicine["clinically_verified"] is False
    assert medicine["external"] is True


def test_lookup_rxnorm_preserves_raw_score_without_percentage_conversion():
    payload = {
        "approximateGroup": {
            "candidate": [
                {
                    "rxcui": "999",
                    "score": "12.788553237915039",
                    "rank": "1",
                    "name": "Example Medicine",
                }
            ]
        }
    }

    with patch(
        "backend.services.external_medicine_knowledge._http_get_json",
        return_value=payload,
    ):
        result = lookup_rxnorm("example")

    assert len(result) == 1
    assert result[0]["raw_rxnorm_score"] == 12.788553237915039
    assert result[0]["source_confidence"] < 0.78


def test_lookup_rxnorm_uses_candidate_name_without_extra_request():
    payload = {
        "approximateGroup": {
            "candidate": [
                {
                    "rxcui": "123",
                    "score": "20",
                    "rank": "1",
                    "name": "Paracetamol 500 MG Tablet",
                }
            ]
        }
    }

    with patch(
        "backend.services.external_medicine_knowledge._http_get_json",
        return_value=payload,
    ) as mock_get:
        result = lookup_rxnorm("paracetamol")

    assert len(result) == 1
    assert result[0]["normalized_name"] == "Paracetamol 500 MG Tablet"
    assert mock_get.call_count == 1


def test_lookup_rxnorm_falls_back_to_name_lookup():
    approximate_payload = {
        "approximateGroup": {
            "candidate": [
                {
                    "rxcui": "456",
                    "score": "20",
                    "rank": "1",
                }
            ]
        }
    }

    name_payload = {
        "propConceptGroup": {
            "propConcept": [
                {
                    "propValue": "Ibuprofen 400 MG Oral Tablet"
                }
            ]
        }
    }

    with patch(
        "backend.services.external_medicine_knowledge._http_get_json",
        side_effect=[
            approximate_payload,
            name_payload,
        ],
    ) as mock_get:
        result = lookup_rxnorm("ibuprofen")

    assert len(result) == 1
    assert result[0]["normalized_name"] == (
        "Ibuprofen 400 MG Oral Tablet"
    )
    assert mock_get.call_count == 2


def test_lookup_rxnorm_skips_candidate_without_resolvable_name():
    payload = {
        "approximateGroup": {
            "candidate": [
                {
                    "rxcui": "789",
                    "score": "20",
                    "rank": "1",
                }
            ]
        }
    }

    with patch(
        "backend.services.external_medicine_knowledge._http_get_json",
        return_value=payload,
    ):
        result = lookup_rxnorm("unknown")

    assert result == []


def test_lookup_rxnorm_handles_network_failure():
    with patch(
        "backend.services.external_medicine_knowledge._http_get_json",
        side_effect=Exception("network unavailable"),
    ):
        result = lookup_rxnorm("paracetamol")

    assert result == []


def test_lookup_rxnorm_handles_empty_response():
    with patch(
        "backend.services.external_medicine_knowledge._http_get_json",
        return_value={},
    ):
        result = lookup_rxnorm("paracetamol")

    assert result == []


def test_lookup_rxnorm_respects_top_k():
    payload = {
        "approximateGroup": {
            "candidate": [
                {
                    "rxcui": "1",
                    "score": "30",
                    "rank": "1",
                    "name": "Medicine One",
                },
                {
                    "rxcui": "2",
                    "score": "20",
                    "rank": "2",
                    "name": "Medicine Two",
                },
                {
                    "rxcui": "3",
                    "score": "10",
                    "rank": "3",
                    "name": "Medicine Three",
                },
            ]
        }
    }

    with patch(
        "backend.services.external_medicine_knowledge._http_get_json",
        return_value=payload,
    ):
        result = lookup_rxnorm("medicine", top_k=2)

    assert len(result) == 2
    assert result[0]["rxcui"] == "1"
    assert result[1]["rxcui"] == "2"


def test_lookup_external_medicine_delegates_to_rxnorm():
    expected = [
        {
            "normalized_name": "Paracetamol 500 MG Tablet",
            "external": True,
        }
    ]

    with patch(
        "backend.services.external_medicine_knowledge.lookup_rxnorm",
        return_value=expected,
    ) as mock_lookup:
        result = lookup_external_medicine(
            "paracetamol",
            top_k=3,
            timeout=2.0,
        )

    assert result == expected

    mock_lookup.assert_called_once_with(
        "paracetamol",
        top_k=3,
        timeout=2.0,
    )


def test_lookup_external_medicine_fails_closed():
    with patch(
        "backend.services.external_medicine_knowledge.lookup_rxnorm",
        side_effect=Exception("unexpected failure"),
    ):
        result = lookup_external_medicine("paracetamol")

    assert result == []