"""
Tests for the organization usage plan service.

Covers:
  - Plan status retrieval (no DB required — uses pure logic)
  - Monthly limit enforcement
  - Period reset logic
  - Increment usage
  - Never blocking prescription upload on service errors
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from backend.services.usage_plan import (
    PLAN_TIERS,
    _is_new_period,
    check_prescription_limit,
    increment_prescription_usage,
    get_plan_status,
)
from backend.models import OrganizationPlanDB


# =========================================================
# PLAN TIER CONFIGURATION
# =========================================================


def test_plan_tiers_have_required_keys():
    for tier_name, tier in PLAN_TIERS.items():
        assert "display_name" in tier, f"{tier_name} missing display_name"
        assert "monthly_prescription_limit" in tier, f"{tier_name} missing limit"
        assert "review_workflow_enabled" in tier, f"{tier_name} missing review_workflow_enabled"
        assert "pdf_reports_enabled" in tier, f"{tier_name} missing pdf_reports_enabled"


def test_free_tier_has_limit():
    assert PLAN_TIERS["free"]["monthly_prescription_limit"] is not None
    assert PLAN_TIERS["free"]["monthly_prescription_limit"] > 0


def test_enterprise_tier_is_unlimited():
    assert PLAN_TIERS["enterprise"]["monthly_prescription_limit"] is None


def test_professional_tier_limit_exceeds_free():
    free_limit = PLAN_TIERS["free"]["monthly_prescription_limit"]
    pro_limit = PLAN_TIERS["professional"]["monthly_prescription_limit"]
    assert pro_limit > free_limit


# =========================================================
# PERIOD RESET LOGIC
# =========================================================


def _make_plan(period_start: datetime) -> MagicMock:
    plan = MagicMock(spec=OrganizationPlanDB)
    plan.period_start = period_start
    return plan


def test_same_month_is_not_new_period():
    now = datetime.now(timezone.utc)
    plan = _make_plan(period_start=now)
    assert _is_new_period(plan) is False


def test_previous_month_is_new_period():
    last_month = datetime.now(timezone.utc) - timedelta(days=32)
    plan = _make_plan(period_start=last_month)
    assert _is_new_period(plan) is True


def test_previous_year_is_new_period():
    last_year = datetime.now(timezone.utc) - timedelta(days=400)
    plan = _make_plan(period_start=last_year)
    assert _is_new_period(plan) is True


def test_naive_period_start_is_handled():
    # Timezone-naive datetimes from older DB records should not crash.
    naive = datetime.utcnow().replace(day=1)
    plan = _make_plan(period_start=naive)
    # Should not raise
    result = _is_new_period(plan)
    assert isinstance(result, bool)


# =========================================================
# USAGE LIMIT ENFORCEMENT
# =========================================================


def _make_mock_db_for_plan(plan: OrganizationPlanDB) -> MagicMock:
    db = MagicMock()
    mock_query = MagicMock()
    mock_query.filter.return_value.first.return_value = plan
    db.query.return_value = mock_query
    db.add = MagicMock()
    db.flush = MagicMock()
    return db


def test_check_limit_passes_when_under_limit():
    now = datetime.now(timezone.utc)
    plan = MagicMock(spec=OrganizationPlanDB)
    plan.id = uuid4()
    plan.organization_id = uuid4()
    plan.plan_tier = "free"
    plan.monthly_prescription_limit = 25
    plan.period_start = now
    plan.period_prescription_count = 10

    db = _make_mock_db_for_plan(plan)

    # Should not raise
    check_prescription_limit(
        organization_id=plan.organization_id,
        db=db,
    )


def test_check_limit_raises_when_at_limit():
    from fastapi import HTTPException

    now = datetime.now(timezone.utc)
    plan = MagicMock(spec=OrganizationPlanDB)
    plan.id = uuid4()
    plan.organization_id = uuid4()
    plan.plan_tier = "free"
    plan.monthly_prescription_limit = 25
    plan.period_start = now
    plan.period_prescription_count = 25  # At limit

    db = _make_mock_db_for_plan(plan)

    with pytest.raises(HTTPException) as exc_info:
        check_prescription_limit(
            organization_id=plan.organization_id,
            db=db,
        )

    assert exc_info.value.status_code == 429
    assert "limit" in exc_info.value.detail.lower()


def test_check_limit_raises_when_over_limit():
    from fastapi import HTTPException

    now = datetime.now(timezone.utc)
    plan = MagicMock(spec=OrganizationPlanDB)
    plan.id = uuid4()
    plan.organization_id = uuid4()
    plan.plan_tier = "free"
    plan.monthly_prescription_limit = 25
    plan.period_start = now
    plan.period_prescription_count = 30  # Over limit

    db = _make_mock_db_for_plan(plan)

    with pytest.raises(HTTPException) as exc_info:
        check_prescription_limit(
            organization_id=plan.organization_id,
            db=db,
        )

    assert exc_info.value.status_code == 429


def test_check_limit_passes_for_unlimited_plan():
    now = datetime.now(timezone.utc)
    plan = MagicMock(spec=OrganizationPlanDB)
    plan.id = uuid4()
    plan.organization_id = uuid4()
    plan.plan_tier = "enterprise"
    plan.monthly_prescription_limit = None  # Unlimited
    plan.period_start = now
    plan.period_prescription_count = 9999

    db = _make_mock_db_for_plan(plan)

    # Should not raise for unlimited plan
    check_prescription_limit(
        organization_id=plan.organization_id,
        db=db,
    )


def test_check_limit_resets_on_new_period():
    """Usage resets when a new billing period starts — should not block upload."""

    last_month = datetime.now(timezone.utc) - timedelta(days=35)

    plan = MagicMock(spec=OrganizationPlanDB)
    plan.id = uuid4()
    plan.organization_id = uuid4()
    plan.plan_tier = "free"
    plan.monthly_prescription_limit = 25
    plan.period_start = last_month
    plan.period_prescription_count = 25  # Was at limit last month

    db = _make_mock_db_for_plan(plan)

    # Should not raise — new period resets the counter
    check_prescription_limit(
        organization_id=plan.organization_id,
        db=db,
    )


def test_check_limit_does_not_raise_on_service_error():
    """
    A service error must never block a prescription upload.
    """

    db = MagicMock()
    db.query.side_effect = Exception("DB connection lost")

    # Should not raise
    check_prescription_limit(
        organization_id=uuid4(),
        db=db,
    )


# =========================================================
# USAGE INCREMENT
# =========================================================


def test_increment_usage_increases_count():
    now = datetime.now(timezone.utc)
    plan = MagicMock(spec=OrganizationPlanDB)
    plan.id = uuid4()
    plan.organization_id = uuid4()
    plan.plan_tier = "free"
    plan.monthly_prescription_limit = 25
    plan.period_start = now
    plan.period_prescription_count = 5

    db = _make_mock_db_for_plan(plan)

    increment_prescription_usage(
        organization_id=plan.organization_id,
        db=db,
    )

    assert plan.period_prescription_count == 6


def test_increment_usage_resets_on_new_period():
    last_month = datetime.now(timezone.utc) - timedelta(days=35)

    plan = MagicMock(spec=OrganizationPlanDB)
    plan.id = uuid4()
    plan.organization_id = uuid4()
    plan.plan_tier = "free"
    plan.monthly_prescription_limit = 25
    plan.period_start = last_month
    plan.period_prescription_count = 24

    db = _make_mock_db_for_plan(plan)

    increment_prescription_usage(
        organization_id=plan.organization_id,
        db=db,
    )

    # New period: counter resets to 1
    assert plan.period_prescription_count == 1


def test_increment_usage_does_not_raise_on_error():
    """
    Service errors must never fail a prescription upload.
    """

    db = MagicMock()
    db.query.side_effect = Exception("DB error")

    # Should not raise
    increment_prescription_usage(
        organization_id=uuid4(),
        db=db,
    )


# =========================================================
# GET PLAN STATUS
# =========================================================


def test_get_plan_status_returns_expected_fields():
    now = datetime.now(timezone.utc)
    plan = MagicMock(spec=OrganizationPlanDB)
    plan.id = uuid4()
    plan.organization_id = uuid4()
    plan.plan_tier = "free"
    plan.monthly_prescription_limit = 25
    plan.period_start = now
    plan.period_prescription_count = 10
    plan.review_workflow_enabled = True
    plan.pdf_reports_enabled = False

    db = _make_mock_db_for_plan(plan)

    status = get_plan_status(
        organization_id=plan.organization_id,
        db=db,
    )

    assert status["plan_tier"] == "free"
    assert status["monthly_limit"] == 25
    assert status["prescriptions_used_this_period"] == 10
    assert status["prescriptions_remaining"] == 15
    assert status["at_limit"] is False
    assert status["review_workflow_enabled"] is True
    assert status["pdf_reports_enabled"] is False


def test_get_plan_status_unlimited_has_none_remaining():
    now = datetime.now(timezone.utc)
    plan = MagicMock(spec=OrganizationPlanDB)
    plan.id = uuid4()
    plan.organization_id = uuid4()
    plan.plan_tier = "enterprise"
    plan.monthly_prescription_limit = None
    plan.period_start = now
    plan.period_prescription_count = 999
    plan.review_workflow_enabled = True
    plan.pdf_reports_enabled = True

    db = _make_mock_db_for_plan(plan)

    status = get_plan_status(
        organization_id=plan.organization_id,
        db=db,
    )

    assert status["monthly_limit"] is None
    assert status["prescriptions_remaining"] is None
    assert status["at_limit"] is False


def test_get_plan_status_returns_default_on_error():
    db = MagicMock()
    db.query.side_effect = Exception("DB error")

    status = get_plan_status(
        organization_id=uuid4(),
        db=db,
    )

    # Should return a safe default
    assert "plan_tier" in status
    assert "at_limit" in status
    assert status["at_limit"] is False


# =========================================================
# UP-1 / UP-2 REGRESSION: fail-open preserved, warnings emitted
# =========================================================


def test_check_limit_logs_warning_on_service_error(caplog):
    """
    UP-1: A service error must never block a prescription upload,
    AND a warning must be logged so the bypass is operationally visible.
    """
    import logging

    db = MagicMock()
    db.query.side_effect = Exception("DB connection lost")

    with caplog.at_level(logging.WARNING, logger="backend.services.usage_plan"):
        # Must not raise — fail-open is preserved
        check_prescription_limit(
            organization_id=uuid4(),
            db=db,
        )

    # A warning must have been emitted
    assert any("quota" in record.message.lower() or "limit" in record.message.lower()
               for record in caplog.records), (
        "UP-1: Expected a warning log when quota check fails"
    )


def test_increment_usage_logs_warning_on_service_error(caplog):
    """
    UP-2: A service error during usage increment must not fail the upload,
    AND a warning must be logged so metering inaccuracy is operationally visible.
    """
    import logging

    db = MagicMock()
    db.query.side_effect = Exception("DB error during increment")

    with caplog.at_level(logging.WARNING, logger="backend.services.usage_plan"):
        # Must not raise — fail-open is preserved
        increment_prescription_usage(
            organization_id=uuid4(),
            db=db,
        )

    # A warning must have been emitted
    assert any("increment" in record.message.lower() or "metering" in record.message.lower()
               for record in caplog.records), (
        "UP-2: Expected a warning log when usage increment fails"
    )


def test_check_limit_still_raises_429_when_at_limit(caplog):
    """
    The fail-open logging path must NOT interfere with normal 429 enforcement.
    An org at its limit must still receive HTTP 429.
    """
    from fastapi import HTTPException
    import logging

    now = datetime.now(timezone.utc)
    plan = MagicMock(spec=OrganizationPlanDB)
    plan.id = uuid4()
    plan.organization_id = uuid4()
    plan.plan_tier = "free"
    plan.monthly_prescription_limit = 25
    plan.period_start = now
    plan.period_prescription_count = 25

    db = _make_mock_db_for_plan(plan)

    with caplog.at_level(logging.WARNING, logger="backend.services.usage_plan"):
        with pytest.raises(HTTPException) as exc_info:
            check_prescription_limit(
                organization_id=plan.organization_id,
                db=db,
            )

    # HTTP 429 is still raised — logging did not change quota behavior
    assert exc_info.value.status_code == 429
    # No spurious warning should appear for a normal 429 (it was re-raised cleanly)
    warning_texts = [r.message for r in caplog.records]
    assert not any("quota" in t.lower() or "limit check failed" in t.lower()
                   for t in warning_texts), (
        "No warning should be logged for a normal 429 enforcement"
    )
