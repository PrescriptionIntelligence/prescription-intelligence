from backend.services.prescription_pipeline import (
    _compute_confidence_summary,
)


def _medicine(
    extraction_confidence=0.90,
    normalization_confidence=1.00,
    needs_review=False,
):
    return {
        "extraction_confidence": extraction_confidence,
        "normalization_confidence": normalization_confidence,
        "needs_review": needs_review,
    }


def test_normal_confidence_preserves_95_percent_result():
    result = _compute_confidence_summary(
        [
            _medicine(
                extraction_confidence=0.90,
                normalization_confidence=1.00,
            )
        ]
    )

    assert (
        result["overall_confidence"]
        == 0.95
    )

    assert (
        result["average_extraction_confidence"]
        == 0.90
    )

    assert (
        result["average_normalization_confidence"]
        == 1.00
    )

    assert result["needs_review_count"] == 0
    assert result["verified"] is True


def test_missing_extraction_confidence_requires_review():
    result = _compute_confidence_summary(
        [
            _medicine(
                extraction_confidence=None,
                normalization_confidence=1.00,
            )
        ]
    )

    assert result["overall_confidence"] is None
    assert result["needs_review_count"] == 1
    assert result["verified"] is False


def test_missing_normalization_confidence_requires_review():
    result = _compute_confidence_summary(
        [
            _medicine(
                extraction_confidence=0.90,
                normalization_confidence=None,
            )
        ]
    )

    assert result["overall_confidence"] is None
    assert result["needs_review_count"] == 1
    assert result["verified"] is False


def test_low_confidence_requires_review():
    result = _compute_confidence_summary(
        [
            _medicine(
                extraction_confidence=0.60,
                normalization_confidence=0.95,
            )
        ]
    )

    assert result["overall_confidence"] == 0.775
    assert result["needs_review_count"] == 1
    assert result["verified"] is False


def test_medicine_needing_review_is_counted():
    result = _compute_confidence_summary(
        [
            _medicine(
                extraction_confidence=0.90,
                normalization_confidence=1.00,
                needs_review=True,
            )
        ]
    )

    assert result["overall_confidence"] == 0.95
    assert result["needs_review_count"] == 1
    assert result["verified"] is False


def test_empty_medicine_list_has_no_confidence():
    result = _compute_confidence_summary([])

    assert result["overall_confidence"] is None
    assert result["minimum_confidence"] is None
    assert result["needs_review_count"] == 0
    assert result["verified"] is False