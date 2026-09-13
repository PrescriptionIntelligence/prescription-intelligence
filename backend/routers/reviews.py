from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.auth import require_pharmacist
from backend.database import get_db
from backend.models import (
    PrescriptionDB,
    ReviewAuditDB,
    UserDB,
)
from backend.schemas import (
    ReviewActionRequest,
    ReviewAuditResponse,
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
}

VALID_STATUSES = {
    "pending",
    "under_review",
    "verified",
    "needs_clarification",
    "rejected",
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


def get_high_priority_findings(
    prescription: PrescriptionDB,
) -> list[dict[str, Any]]:

    flags = prescription.safety_flags or []

    return [
        flag
        for flag in flags
        if isinstance(flag, dict)
        and str(flag.get("severity", "")).lower()
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


def determine_new_status(
    prescription: PrescriptionDB,
    action: str,
) -> str:

    high_priority = get_high_priority_findings(
        prescription
    )

    # -----------------------------------------------------
    # Start review
    # -----------------------------------------------------

    if action == "start_review":
        return "under_review"

    # -----------------------------------------------------
    # Clarification
    # -----------------------------------------------------

    if action == "clarify":
        return "needs_clarification"

    # -----------------------------------------------------
    # Explicit rejection
    # -----------------------------------------------------

    if action == "dismiss":
        return "rejected"

    # -----------------------------------------------------
    # Correction
    # -----------------------------------------------------

    if action == "correct":

        if high_priority:
            return "under_review"

        return "verified"

    # -----------------------------------------------------
    # Confirmation
    # -----------------------------------------------------

    if action == "confirm":

        # Critical safety rule:
        #
        # A prescription containing high-priority findings
        # cannot become verified merely because the reviewer
        # presses "confirm".
        #
        # The reviewer must explicitly resolve/correct the
        # finding first.
        if high_priority:
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

    high_priority = get_high_priority_findings(
        prescription
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
        "review_status": (
            prescription.review_status
            or "pending"
        ),
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
    # Resolve new status
    # -----------------------------------------------------

    new_status = determine_new_status(
        prescription,
        request.action,
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

        if request.finding.finding_index is not None:
            finding_data[
                "finding_index"
            ] = request.finding.finding_index

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

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Failed to save prescription review: "
                f"{str(exc)}"
            ),
        )

    high_priority = get_high_priority_findings(
        prescription
    )

    return {
        "prescription_id": prescription.prescription_id,
        "review_status": (
            prescription.review_status
        ),
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
            ReviewAuditDB.created_at.asc()
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