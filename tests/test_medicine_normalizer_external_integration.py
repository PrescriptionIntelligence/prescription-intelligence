from unittest.mock import patch

import backend.services.medicine_normalizer as medicine_normalizer


def _local_medicine():
    return {
        "brand_name": "Amoxil",
        "generic_name": "Amoxicillin",
        "strength_value": "500",
        "strength_unit": "mg",
        "dosage_form": "Tablet",
    }


def _candidate(text="amoxil"):
    return {
        "medicine_text": text,
    }


def _external_hypothesis():
    return {
        "normalized_name": "Amoxicillin",
        "generic_name": "Amoxicillin",
        "matched_term": "amoxil",
        "rxcui": "723",
        "raw_rxnorm_score": 20.0,
        "rank": 1,
        "source": "RxNorm",
        "source_id": "723",
        "match_method": "approximate_term",
        "source_confidence": 0.74,
        "clinically_verified": False,
        "external": True,
    }


def test_strong_local_match_does_not_call_external_lookup():
    medicines = [_local_medicine()]

    with patch.object(
        medicine_normalizer,
        "_score_medicine",
        return_value={
            "score": 0.95,
            "token_score": 0.95,
            "full_score": 0.95,
            "matched_term": "amoxil",
        },
    ), patch.object(
        medicine_normalizer,
        "lookup_external_medicine",
    ) as external_lookup:

        results = medicine_normalizer.get_ranked_medicine_hypotheses(
            _candidate(),
            medicines=medicines,
            top_k=3,
        )

    external_lookup.assert_not_called()

    assert len(results) == 1
    assert results[0]["normalized_name"] == "Amoxil"
    assert results[0]["source"] == "curated"
    assert results[0]["external"] is False


def test_weak_local_match_queries_external_knowledge():
    medicines = [_local_medicine()]

    external = {
        **_external_hypothesis(),
        "normalized_name": "Azithromycin",
        "generic_name": "Azithromycin",
        "matched_term": "amoxil",
        "rxcui": "18631",
        "source_id": "18631",
    }

    with patch.object(
        medicine_normalizer,
        "_score_medicine",
        return_value={
            "score": 0.40,
            "token_score": 0.40,
            "full_score": 0.40,
            "matched_term": "amoxil",
        },
    ), patch.object(
        medicine_normalizer,
        "lookup_external_medicine",
        return_value=[external],
    ) as external_lookup:

        results = medicine_normalizer.get_ranked_medicine_hypotheses(
            _candidate(),
            medicines=medicines,
            top_k=3,
        )

    external_lookup.assert_called_once()

    assert results
    assert any(
        result.get("external") is True
        for result in results
    )

def test_external_hypothesis_is_never_allowed_to_exceed_external_cap():
    hypothesis = {
        **_external_hypothesis(),
        "source_confidence": 0.99,
    }

    converted = medicine_normalizer._convert_external_hypothesis(
        hypothesis
    )

    assert converted is not None
    assert converted["score"] <= 0.74
    assert converted["source_confidence"] == 0.99
    assert converted["external"] is True
    assert converted["clinically_verified"] is False


def test_external_hypothesis_is_not_clinically_verified():
    converted = medicine_normalizer._convert_external_hypothesis(
        _external_hypothesis()
    )

    assert converted is not None
    assert converted["external"] is True
    assert converted["clinically_verified"] is False


def test_local_curated_result_is_preferred_when_duplicate_external_identity_exists():
    medicines = [_local_medicine()]

    external = {
        **_external_hypothesis(),
        "generic_name": "Amoxicillin",
        "normalized_name": "Amoxicillin",
        "source_confidence": 0.70,
    }

    with patch.object(
        medicine_normalizer,
        "_score_medicine",
        return_value={
            "score": 0.50,
            "token_score": 0.50,
            "full_score": 0.50,
            "matched_term": "amoxil",
        },
    ), patch.object(
        medicine_normalizer,
        "lookup_external_medicine",
        return_value=[external],
    ):

        results = medicine_normalizer.get_ranked_medicine_hypotheses(
            _candidate(),
            medicines=medicines,
            top_k=3,
        )

    matching = [
        result
        for result in results
        if result.get("generic_name") == "Amoxicillin"
    ]

    assert len(matching) == 1
    assert matching[0]["external"] is False
    assert matching[0]["source"] == "curated"


def test_external_lookup_failure_preserves_local_results():
    medicines = [_local_medicine()]

    with patch.object(
        medicine_normalizer,
        "_score_medicine",
        return_value={
            "score": 0.40,
            "token_score": 0.40,
            "full_score": 0.40,
            "matched_term": "amoxil",
        },
    ), patch.object(
        medicine_normalizer,
        "lookup_external_medicine",
        side_effect=RuntimeError("RxNorm unavailable"),
    ):

        results = medicine_normalizer.get_ranked_medicine_hypotheses(
            _candidate(),
            medicines=medicines,
            top_k=3,
        )

    assert results
    assert results[0]["source"] == "curated"
    assert results[0]["external"] is False