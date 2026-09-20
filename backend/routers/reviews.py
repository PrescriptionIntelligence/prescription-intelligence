import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from backend.auth import require_pharmacist
from backend.database import get_db
from backend.models import (
    PrescriptionDB,
    ReviewAuditDB,
    UserDB,
)
from backend.schemas import (
    ReviewActionRequest,
    ReviewHistoryResponse,
    ReviewStatusResponse,
)


router = APIRouter(
    prefix="/prescriptions",
    tags=["Prescription Review"],
)


# =========================================================
# CONSTANTS
# =========================================================

VALID_ACTIONS = {
    "start_review",
    "confirm",
    "correct",
    "dismiss",
    "clarify",
    "complete_review",
}

VALID_STATUSES = {
    "pending",
    "under_review",
    "verified",
    "needs_clarification",
    "rejected",
}

RESOLVING_ACTIONS = {
    "confirm",
    "correct",
    "dismiss",
    "complete_review",
}


# =========================================================
# HELPERS
# =========================================================

def get_owned_prescription(
    prescription_id: str,
    current_user: UserDB,
    db: Session,
) -> PrescriptionDB:

    prescription = (
        db.query(PrescriptionDB)
        .filter(
            PrescriptionDB.prescription_id
            == prescription_id
        )
        .first()
    )

    if not prescription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prescription not found",
        )

    # -----------------------------------------------------
    # Organization isolation
    # -----------------------------------------------------

    if (
        prescription.organization_id is None
        or current_user.organization_id is None
        or prescription.organization_id
        != current_user.organization_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "You do not have access to this prescription."
            ),
        )

    return prescription


def get_all_findings(
    prescription: PrescriptionDB,
) -> list[dict[str, Any]]:
    """
    Return only dictionary-based safety findings.

    The original AI findings are never modified by the
    review workflow.
    """

    flags = prescription.safety_flags or []

    return [
        flag
        for flag in flags
        if isinstance(flag, dict)
    ]


def get_high_priority_findings(
    prescription: PrescriptionDB,
) -> list[dict[str, Any]]:

    findings = get_all_findings(prescription)

    return [
        finding
        for finding in findings
        if str(
            finding.get("severity", "")
        ).lower()
        in {
            "high",
            "critical",
            "error",
        }
    ]


def get_finding_key(
    finding_index: int,
) -> str:
    """
    Generate the stable identity used by the review audit
    history for a finding.

    Finding identity is intentionally based on the finding's
    position within the immutable prescription analysis.
    """

    return f"finding:{finding_index}"


def get_finding_index_from_audit(
    audit: ReviewAuditDB,
) -> int | None:

    if not audit.finding_data:
        return None

    value = audit.finding_data.get(
        "finding_index"
    )

    if isinstance(value, int):
        return value

    return None


def get_resolved_finding_indexes(
    prescription: PrescriptionDB,
    db: Session,
) -> set[int]:
    """
    Determine which findings have been resolved by the
    latest pharmacist action.

    The original safety_flags remain unchanged.

    Only confirm/correct/dismiss resolve a finding.
    Clarification does not resolve it.
    """

    audits = (
        db.query(ReviewAuditDB)
        .filter(
            ReviewAuditDB.prescription_id
            == prescription.id
        )
        .order_by(
            ReviewAuditDB.created_at.asc(),
            ReviewAuditDB.id.asc(),
        )
        .all()
    )

    latest_actions: dict[int, str] = {}

    for audit in audits:
        finding_index = (
            get_finding_index_from_audit(audit)
        )

        if finding_index is None:
            continue

        latest_actions[
            finding_index
        ] = audit.action

    return {
        finding_index
        for finding_index, action
        in latest_actions.items()
        if action in RESOLVING_ACTIONS
    }


def get_unresolved_findings(
    prescription: PrescriptionDB,
    db: Session,
) -> list[dict[str, Any]]:

    findings = get_all_findings(prescription)

    resolved_indexes = (
        get_resolved_finding_indexes(
            prescription,
            db,
        )
    )

    return [
        finding
        for index, finding
        in enumerate(findings)
        if index not in resolved_indexes
    ]


def get_unresolved_high_priority_findings(
    prescription: PrescriptionDB,
    db: Session,
) -> list[dict[str, Any]]:

    unresolved = get_unresolved_findings(
        prescription,
        db,
    )

    return [
        finding
        for finding in unresolved
        if str(
            finding.get("severity", "")
        ).lower()
        in {
            "high",
            "critical",
            "error",
        }
    ]


def validate_action(action: str) -> None:

    if action not in VALID_ACTIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid review action '{action}'. "
                f"Allowed actions: "
                f"{', '.join(sorted(VALID_ACTIONS))}"
            ),
        )


def validate_finding(
    prescription: PrescriptionDB,
    request: ReviewActionRequest,
) -> None:
    """
    Validate that the requested finding actually exists and
    that the supplied finding type matches the immutable
    AI-generated finding at that index.
    """

    if request.action in {
        "start_review",
        "complete_review",
    }:
        return

    if request.finding is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "A finding is required for this review action."
            ),
        )

    finding_index = (
        request.finding.finding_index
    )

    if finding_index is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Finding index is required for this "
                "review action."
            ),
        )

    findings = get_all_findings(
        prescription
    )

    if finding_index >= len(findings):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Finding index {finding_index} "
                "is out of range."
            ),
        )

    actual_finding = findings[
        finding_index
    ]

    actual_type = str(
        actual_finding.get(
            "type",
            actual_finding.get(
                "finding_type",
                "",
            ),
        )
    ).strip().lower()

    requested_type = (
        request.finding.finding_type
        .strip()
        .lower()
    )

    if actual_type != requested_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Finding type '{request.finding.finding_type}' "
                f"does not match the finding at index "
                f"{finding_index}."
            ),
        )


def determine_new_status(
    prescription: PrescriptionDB,
    action: str,
    db: Session,
    finding_index: int | None = None,
) -> str:
    unresolved_high_priority = (
        get_unresolved_high_priority_findings(
            prescription,
            db,
        )
    )

    current_finding = None

    if (
        action in RESOLVING_ACTIONS
        and finding_index is not None
    ):
        findings = get_all_findings(prescription)

        if 0 <= finding_index < len(findings):
            current_finding = findings[finding_index]

            current_severity = str(
                current_finding.get(
                    "severity",
                    "",
                )
            ).lower()

            if current_severity in {
                "high",
                "critical",
                "error",
            }:
                unresolved_high_priority = [
                    finding
                    for finding in unresolved_high_priority
                    if finding is not current_finding
                ]

    if action == "complete_review":
        unresolved_findings = get_unresolved_findings(
            prescription,
            db,
        )

        if unresolved_findings:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "All safety findings must be resolved "
                    "before completing the pharmacist review."
                ),
            )

        if prescription.review_status != "under_review":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Prescription must be under review "
                    "before it can be completed."
                ),
            )

        return "verified"

    if action == "start_review":
        return "under_review"

    if action == "clarify":
        return "needs_clarification"

    if action == "dismiss":
        if unresolved_high_priority:
            return "under_review"

        if (
            current_finding is not None
            and str(
                current_finding.get(
                    "severity",
                    "",
                )
            ).lower()
            in {"high", "critical", "error"}
        ):
            return "rejected"

        return "verified"

    if action == "correct":
        if unresolved_high_priority:
            return "under_review"
        return "verified"

    if action == "confirm":
        if unresolved_high_priority:
            return "under_review"
        return "verified"

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Unable to determine review status",
    )


# =========================================================
# GET REVIEW STATUS
# =========================================================

@router.get(
    "/{prescription_id}/review",
    response_model=ReviewStatusResponse,
)
def get_review_status(
    prescription_id: str,
    current_user: UserDB = Depends(
        require_pharmacist
    ),
    db: Session = Depends(get_db),
):

    prescription = get_owned_prescription(
        prescription_id,
        current_user,
        db,
    )

    high_priority = (
        get_unresolved_high_priority_findings(
            prescription,
            db,
        )
    )

    unresolved = get_unresolved_findings(
        prescription,
        db,
    )

    current_status = (
        prescription.review_status or "pending"
    )

    # complete_review requires under_review status
    # AND all findings resolved.
    can_complete = (
        current_status == "under_review"
        and len(unresolved) == 0
    )

    reviewer = None

    if prescription.reviewed_by:
        reviewer = {
            "id": str(
                prescription.reviewed_by.id
            ),
            "name": prescription.reviewed_by.name,
            "email": prescription.reviewed_by.email,
            "role": prescription.reviewed_by.role,
        }

    return {
        "prescription_id": prescription.prescription_id,
        "review_status": current_status,
        "reviewed_by_id": (
            prescription.reviewed_by_id
        ),
        "reviewed_at": (
            prescription.reviewed_at
        ),
        "review_notes": (
            prescription.review_notes
        ),
        "reviewer": reviewer,
        "high_priority_findings": len(
            high_priority
        ),
        "total_findings": len(
            prescription.safety_flags or []
        ),
        "unresolved_findings": len(unresolved),
        "can_complete_review": can_complete,
    }


# =========================================================
# PERFORM REVIEW ACTION
# =========================================================

@router.post(
    "/{prescription_id}/review",
    response_model=ReviewStatusResponse,
)
def review_prescription(
    prescription_id: str,
    request: ReviewActionRequest,
    current_user: UserDB = Depends(
        require_pharmacist
    ),
    db: Session = Depends(get_db),
):

    validate_action(request.action)

    prescription = get_owned_prescription(
        prescription_id,
        current_user,
        db,
    )

    validate_finding(
        prescription,
        request,
    )

    previous_status = (
        prescription.review_status
        or "pending"
    )

    # -----------------------------------------------------
    # Prevent meaningless repeated final actions
    # -----------------------------------------------------

    if (
        previous_status == "verified"
        and request.action
        in {
            "confirm",
            "start_review",
        }
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Prescription is already verified."
            ),
        )

    # -----------------------------------------------------
    # Determine new prescription status
    # -----------------------------------------------------

    new_status = determine_new_status(
        prescription,
        request.action,
        db,
        (
            request.finding.finding_index
            if request.finding
            else None
        ),
    )

    now = datetime.now(timezone.utc)

    # -----------------------------------------------------
    # Audit finding snapshot
    # -----------------------------------------------------

    finding_type = None
    finding_data = None

    if request.finding:

        finding_type = (
            request.finding.finding_type
        )

        finding_data = dict(
            request.finding.finding_data
        )

        finding_index = (
            request.finding.finding_index
        )

        if finding_index is not None:
            finding_data[
                "finding_index"
            ] = finding_index

            finding_data[
                "finding_key"
            ] = get_finding_key(
                finding_index
            )

    # -----------------------------------------------------
    # Update prescription review state
    # -----------------------------------------------------

    prescription.review_status = new_status

    if request.action != "start_review":
        prescription.reviewed_by_id = (
            current_user.id
        )

        prescription.reviewed_at = now

    if request.note:
        prescription.review_notes = request.note

    # -----------------------------------------------------
    # Immutable audit record
    # -----------------------------------------------------

    audit = ReviewAuditDB(
        prescription_id=prescription.id,
        reviewer_id=current_user.id,
        action=request.action,
        previous_status=previous_status,
        new_status=new_status,
        finding_type=finding_type,
        finding_data=finding_data,
        note=request.note,
        created_at=now,
    )

    db.add(audit)

    try:
        db.commit()
        db.refresh(prescription)

    except Exception as exc:
        db.rollback()

        logger.exception("Failed to save prescription review: %s", exc)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred. Please try again or contact support.",
        )

    high_priority = (
        get_unresolved_high_priority_findings(
            prescription,
            db,
        )
    )

    unresolved_after = get_unresolved_findings(
        prescription,
        db,
    )

    new_review_status = (
        prescription.review_status or "pending"
    )

    can_complete_after = (
        new_review_status == "under_review"
        and len(unresolved_after) == 0
    )

    return {
        "prescription_id": prescription.prescription_id,
        "review_status": new_review_status,
        "reviewed_by_id": (
            prescription.reviewed_by_id
        ),
        "reviewed_at": (
            prescription.reviewed_at
        ),
        "review_notes": (
            prescription.review_notes
        ),
        "reviewer": {
            "id": str(current_user.id),
            "name": current_user.name,
            "email": current_user.email,
            "role": current_user.role,
        },
        "high_priority_findings": len(
            high_priority
        ),
        "total_findings": len(
            prescription.safety_flags or []
        ),
        "unresolved_findings": len(unresolved_after),
        "can_complete_review": can_complete_after,
    }


# =========================================================
# REVIEW AUDIT HISTORY
# =========================================================

@router.get(
    "/{prescription_id}/review/history",
    response_model=ReviewHistoryResponse,
)
def get_review_history(
    prescription_id: str,
    current_user: UserDB = Depends(
        require_pharmacist
    ),
    db: Session = Depends(get_db),
):

    prescription = get_owned_prescription(
        prescription_id,
        current_user,
        db,
    )

    audits = (
        db.query(ReviewAuditDB)
        .filter(
            ReviewAuditDB.prescription_id
            == prescription.id
        )
        .order_by(
            ReviewAuditDB.created_at.asc(),
            ReviewAuditDB.id.asc(),
        )
        .all()
    )

    return {
        "prescription_id": (
            prescription.prescription_id
        ),
        "current_status": (
            prescription.review_status
            or "pending"
        ),
        "audits": audits,
    }