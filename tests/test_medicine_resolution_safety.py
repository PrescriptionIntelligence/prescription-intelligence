from backend.services.medicine_resolver import (
    resolve_medicine_candidate,
)
from backend.services.medicine_evidence import (
    calculate_strength_evidence,
)


def _candidate(
    text="Amoxil",
    extraction_confidence=0.95,
    ocr_confidence=None,
    strength_value="500",
    strength_unit="mg",
):
    return {
        "medicine_text": text,
        "extraction_confidence": extraction_confidence,
        "ocr_confidence": (
            extraction_confidence
            if ocr_confidence is None
            else ocr_confidence
        ),
        "strength_value": strength_value,
        "strength_unit": strength_unit,
    }


def _hypothesis(
    name="Amoxil",
    score=0.95,
    strength_value="500",
    strength_unit="mg",
    external=False,
):
    return {
        "normalized_name": name,
        "generic_name": "Amoxicillin",
        "matched_term": name,
        "score": score,
        "strength_value": strength_value,
        "strength_unit": strength_unit,
        "external": external,
        "source": "RxNorm" if external else "curated",
    }


def test_strong_local_match_is_accepted():
    candidate = _candidate()

    result = resolve_medicine_candidate(
        candidate,
        [_hypothesis(score=0.95)],
    )

    assert result["status"] == "accepted"
    assert (
        result["top_hypothesis"]["normalized_name"]
        == "Amoxil"
    )
    assert (
        result["evidence"]["external_hypothesis"]
        is False
    )


def test_external_hypothesis_always_requires_review():
    candidate = _candidate()

    result = resolve_medicine_candidate(
        candidate,
        [
            _hypothesis(
                score=0.99,
                external=True,
            )
        ],
    )

    assert result["status"] == "needs_review"
    assert (
        result["reason"]
        == "external_hypothesis_requires_review"
    )
    assert (
        result["evidence"]["external_hypothesis"]
        is True
    )


def test_strength_conflict_requires_review():
    candidate = _candidate(
        strength_value="500",
        strength_unit="mg",
    )

    result = resolve_medicine_candidate(
        candidate,
        [
            _hypothesis(
                score=0.99,
                strength_value="250",
                strength_unit="mg",
            )
        ],
    )

    assert result["status"] == "needs_review"
    assert (
        result["evidence"]["strength_compatible"]
        is False
    )
    assert (
        result["reason"] == "strength_conflict"
    )


def test_low_ocr_confidence_requires_review():
    candidate = _candidate(
        extraction_confidence=0.95,
        ocr_confidence=0.30,
    )

    result = resolve_medicine_candidate(
        candidate,
        [_hypothesis(score=0.99)],
    )

    assert result["status"] == "needs_review"
    assert (
        result["reason"]
        == "poor_ocr_confidence"
    )
    assert (
        result["evidence"]["ocr_confidence"]
        == 0.30
    )


def test_close_hypotheses_require_review():
    candidate = _candidate()

    result = resolve_medicine_candidate(
        candidate,
        [
            _hypothesis(
                name="Amoxil",
                score=0.90,
            ),
            _hypothesis(
                name="Amoxicillin",
                score=0.84,
            ),
        ],
    )

    assert result["status"] == "needs_review"
    assert (
        result["evidence"]["margin"] < 0.10
    )
    assert (
        result["reason"] == "ambiguous_match"
    )


def test_weak_match_does_not_become_accepted():
    candidate = _candidate()

    result = resolve_medicine_candidate(
        candidate,
        [_hypothesis(score=0.50)],
    )

    assert result["status"] == "needs_review"


def test_unknown_match_is_not_accepted():
    candidate = _candidate()

    result = resolve_medicine_candidate(
        candidate,
        [_hypothesis(score=0.20)],
    )

    assert result["status"] == "unknown"


def test_exact_strength_has_full_strength_evidence():
    candidate = _candidate(
        strength_value="500",
        strength_unit="mg",
    )

    hypothesis = _hypothesis(
        strength_value="500",
        strength_unit="mg",
    )

    evidence = calculate_strength_evidence(
        candidate,
        hypothesis,
    )

    assert evidence == 1.0


def test_conflicting_strength_has_zero_strength_evidence():
    candidate = _candidate(
        strength_value="500",
        strength_unit="mg",
    )

    hypothesis = _hypothesis(
        strength_value="250",
        strength_unit="mg",
    )

    evidence = calculate_strength_evidence(
        candidate,
        hypothesis,
    )

    assert evidence == 0.0


def test_missing_strength_is_neutral_not_positive():
    candidate = _candidate(
        strength_value=None,
        strength_unit=None,
    )

    hypothesis = _hypothesis(
        strength_value=None,
        strength_unit=None,
    )

    evidence = calculate_strength_evidence(
        candidate,
        hypothesis,
    )

    assert evidence == 0.5