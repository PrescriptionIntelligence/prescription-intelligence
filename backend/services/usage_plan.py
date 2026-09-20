"""
Organization usage plan service.

Handles:
  - Plan-based feature access control
  - Monthly prescription limit enforcement (server-side)
  - Period reset logic
  - Usage increment on successful prescription upload

Architecture note:
  This service provides the foundation for monetization without
  implementing billing. Limits are enforced server-side, not only
  in the frontend.

Plan tiers:
  free:         25 prescriptions/month, basic review
  professional: 500 prescriptions/month, full review + PDF reports
  enterprise:   unlimited, all features

The OrganizationPlanDB row is created on first use if it doesn't
exist, defaulting to the free tier.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.models import OrganizationPlanDB

logger = logging.getLogger(__name__)


# =========================================================
# PLAN TIER DEFINITIONS
# =========================================================

PLAN_TIERS: dict[str, dict[str, Any]] = {
    "free": {
        "display_name": "Free",
        "monthly_prescription_limit": 25,
        "review_workflow_enabled": True,
        "pdf_reports_enabled": False,
        "description": "Limited prescription analysis for evaluation.",
    },
    "professional": {
        "display_name": "Professional",
        "monthly_prescription_limit": 500,
        "review_workflow_enabled": True,
        "pdf_reports_enabled": True,
        "description": "Suitable for independent pharmacies and small clinics.",
    },
    "enterprise": {
        "display_name": "Enterprise",
        "monthly_prescription_limit": None,  # unlimited
        "review_workflow_enabled": True,
        "pdf_reports_enabled": True,
        "description": "Organization-wide workflows, higher limits, full analytics.",
    },
}


def _get_or_create_plan(
    organization_id: Any,
    db: Session,
) -> OrganizationPlanDB:
    """
    Get the organization's plan record, creating a free-tier
    default if one doesn't exist yet.
    """

    plan = (
        db.query(OrganizationPlanDB)
        .filter(
            OrganizationPlanDB.organization_id
            == organization_id
        )
        .first()
    )

    if plan is None:
        plan = OrganizationPlanDB(
            organization_id=organization_id,
            plan_tier="free",
            monthly_prescription_limit=25,
            period_start=datetime.now(timezone.utc),
            period_prescription_count=0,
            review_workflow_enabled=True,
            pdf_reports_enabled=False,
        )

        db.add(plan)
        db.flush()  # Assign ID without committing.

    return plan


def _is_new_period(plan: OrganizationPlanDB) -> bool:
    """
    Return True if the plan's usage period has rolled over
    (i.e. the current month is different from period_start).
    """

    now = datetime.now(timezone.utc)

    period_start = plan.period_start

    # Make period_start timezone-aware if needed.
    if period_start.tzinfo is None:
        period_start = period_start.replace(
            tzinfo=timezone.utc
        )

    return (
        now.year != period_start.year
        or now.month != period_start.month
    )


def get_plan_status(
    organization_id: Any,
    db: Session,
) -> dict[str, Any]:
    """
    Return the organization's current plan status.

    Never raises — returns a default free-tier status on any error.
    """

    try:
        plan = _get_or_create_plan(
            organization_id,
            db,
        )

        tier_info = PLAN_TIERS.get(
            plan.plan_tier,
            PLAN_TIERS["free"],
        )

        limit = plan.monthly_prescription_limit

        if _is_new_period(plan):
            used = 0
        else:
            used = plan.period_prescription_count

        remaining = (
            max(0, limit - used)
            if limit is not None
            else None
        )

        return {
            "plan_tier": plan.plan_tier,
            "display_name": tier_info["display_name"],
            "monthly_limit": limit,
            "prescriptions_used_this_period": used,
            "prescriptions_remaining": remaining,
            "review_workflow_enabled": (
                plan.review_workflow_enabled
            ),
            "pdf_reports_enabled": (
                plan.pdf_reports_enabled
            ),
            "at_limit": (
                limit is not None
                and used >= limit
            ),
        }

    except Exception:
        return {
            "plan_tier": "free",
            "display_name": "Free",
            "monthly_limit": 25,
            "prescriptions_used_this_period": 0,
            "prescriptions_remaining": 25,
            "review_workflow_enabled": True,
            "pdf_reports_enabled": False,
            "at_limit": False,
        }


def check_prescription_limit(
    organization_id: Any,
    db: Session,
) -> None:
    """
    Raise HTTP 429 if the organization has reached its monthly
    prescription analysis limit.

    This is the server-side enforcement point. Never bypass.
    """

    try:
        plan = _get_or_create_plan(
            organization_id,
            db,
        )

        # Reset usage count at the start of a new period.
        if _is_new_period(plan):
            plan.period_prescription_count = 0
            plan.period_start = datetime.now(timezone.utc)
            db.flush()

        limit = plan.monthly_prescription_limit

        # None means unlimited.
        if limit is None:
            return

        if plan.period_prescription_count >= limit:
            tier_info = PLAN_TIERS.get(
                plan.plan_tier,
                PLAN_TIERS["free"],
            )

            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Monthly prescription analysis limit reached "
                    f"({limit} on {tier_info['display_name']} plan). "
                    "Please contact support to upgrade your plan."
                ),
                headers={
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

    except HTTPException:
        raise

    except Exception as exc:
        # Never block prescription processing due to a plan
        # service error. Log and continue.
        logger.warning(
            "Usage limit check failed for org %s — "
            "proceeding without quota enforcement: %s",
            organization_id,
            exc,
        )


def increment_prescription_usage(
    organization_id: Any,
    db: Session,
) -> None:
    """
    Atomically increment the organization's prescription usage counter
    for the current period.

    Called after a successful prescription analysis upload.
    This must be called inside an existing transaction.

    Concurrency safety:
        Uses a SQL-level UPDATE with a column expression
        (count = count + 1) so that concurrent transactions each
        observe the committed value rather than a Python-cached copy.
        This prevents the lost-update race where two simultaneous
        uploads both read the same count and both write count+1.

        Period-reset (new billing month) still goes through ORM
        assignment because it resets to 1 and updates period_start
        simultaneously; that path is inherently single-increment so
        the race is not relevant there.
    """

    try:
        plan = _get_or_create_plan(
            organization_id,
            db,
        )

        if _is_new_period(plan):
            # New billing period: reset counter to 1 and record
            # the new period start.  ORM assignment is safe here
            # because a new period is always a reset-to-1, not an
            # accumulation; no lost-update risk.
            plan.period_prescription_count = 1
            plan.period_start = datetime.now(timezone.utc)
            db.flush()
        else:
            # Same billing period: use a SQL-level atomic increment
            # so concurrent transactions cannot lose updates.
            #
            # synchronize_session="evaluate" keeps the in-memory ORM
            # object consistent without an extra SELECT round-trip.
            db.execute(
                update(OrganizationPlanDB)
                .where(OrganizationPlanDB.id == plan.id)
                .values(
                    period_prescription_count=(
                        OrganizationPlanDB.period_prescription_count + 1
                    )
                )
                .execution_options(synchronize_session="evaluate")
            )
            # Flush so the counter change is visible to subsequent
            # queries in the same transaction (e.g. check_prescription_limit).
            db.flush()

    except Exception as exc:
        # Never fail a prescription upload because of a usage
        # tracking error.
        logger.warning(
            "Usage increment failed for org %s — "
            "usage metering may be inaccurate: %s",
            organization_id,
            exc,
        )
