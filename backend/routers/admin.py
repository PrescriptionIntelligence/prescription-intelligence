from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.auth import require_admin
from backend.database import get_db
from backend.models import (
    OrganizationDB,
    PrescriptionDB,
    ReviewAuditDB,
    UserDB,
)
from backend.schemas import ReviewActionRequest


router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
)


# ============================================================
# HELPERS
# ============================================================


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


def get_finding_summary(
    prescription: PrescriptionDB,
) -> dict[str, Any]:
    flags = prescription.safety_flags or []

    high = 0
    medium = 0
    low = 0
    critical = 0

    for flag in flags:
        if not isinstance(flag, dict):
            continue

        severity = str(
            flag.get("severity", "")
        ).lower()

        if severity == "critical":
            critical += 1
        elif severity == "high":
            high += 1
        elif severity == "medium":
            medium += 1
        elif severity == "low":
            low += 1

    return {
        "total": len(flags),
        "critical": critical,
        "high": high,
        "medium": medium,
        "low": low,
    }


def serialize_prescription(
    prescription: PrescriptionDB,
) -> dict[str, Any]:
    organization = getattr(
        prescription,
        "organization",
        None,
    )

    customer = getattr(
        prescription,
        "customer",
        None,
    )

    uploaded_by = getattr(
        prescription,
        "uploaded_by",
        None,
    )

    reviewed_by = getattr(
        prescription,
        "reviewed_by",
        None,
    )

    findings = get_finding_summary(
        prescription
    )

    return {
        "id": str(prescription.id),
        "prescription_id": prescription.prescription_id,
        "status": prescription.status,
        "review_status": (
            prescription.review_status
            or "pending"
        ),
        "file_name": prescription.file_name,
        "raw_text": prescription.raw_text,
        "organization": (
            {
                "id": str(organization.id),
                "name": organization.name,
                "slug": organization.slug,
            }
            if organization
            else None
        ),
        "customer": (
            {
                "id": str(customer.id),
                "name": getattr(
                    customer,
                    "name",
                    None,
                ),
                "customer_code": getattr(
                    customer,
                    "customer_code",
                    None,
                ),
            }
            if customer
            else None
        ),
        "uploaded_by": (
            {
                "id": str(uploaded_by.id),
                "name": uploaded_by.name,
                "email": uploaded_by.email,
            }
            if uploaded_by
            else None
        ),
        "reviewed_by": (
            {
                "id": str(reviewed_by.id),
                "name": reviewed_by.name,
                "email": reviewed_by.email,
                "role": reviewed_by.role,
            }
            if reviewed_by
            else None
        ),
        "reviewed_at": (
            prescription.reviewed_at.isoformat()
            if prescription.reviewed_at
            else None
        ),
        "review_notes": prescription.review_notes,
        "findings": findings,
        "safety_flags": prescription.safety_flags or [],
    }


# ============================================================
# USERS
# ============================================================


@router.get("/users")
def list_admin_users(
    q: str | None = Query(
        default=None,
        max_length=100,
        description="Search users by name or email",
    ),
    role: str | None = Query(
        default=None,
        description="Filter by role",
    ),
    active: bool | None = Query(
        default=None,
        description="Filter by account status",
    ),
    skip: int = Query(
        default=0,
        ge=0,
    ),
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
    ),
    current_user: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = (
        db.query(UserDB)
        .order_by(UserDB.created_at.desc())
    )

    if q:
        search_term = q.strip()

        if search_term:
            pattern = f"%{search_term}%"

            query = query.filter(
                UserDB.name.ilike(pattern)
                | UserDB.email.ilike(pattern)
            )

    if role:
        allowed_roles = {
            "admin",
            "pharmacist",
            "customer",
        }

        if role not in allowed_roles:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Invalid role. Allowed roles: "
                    "admin, pharmacist, customer"
                ),
            )

        query = query.filter(
            UserDB.role == role
        )

    if active is not None:
        query = query.filter(
            UserDB.is_active == active
        )

    total = query.count()

    users = (
        query
        .offset(skip)
        .limit(limit)
        .all()
    )

    items = []

    for user in users:
        organization = user.organization

        items.append(
            {
                "id": str(user.id),
                "name": user.name,
                "email": user.email,
                "role": user.role,
                "is_active": user.is_active,
                "organization": (
                    {
                        "id": str(organization.id),
                        "name": organization.name,
                        "slug": organization.slug,
                    }
                    if organization
                    else None
                ),
                "created_at": (
                    user.created_at.isoformat()
                    if user.created_at
                    else None
                ),
                "last_login_at": (
                    user.last_login_at.isoformat()
                    if user.last_login_at
                    else None
                ),
            }
        )

    return {
        "items": items,
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/users/stats")
def get_admin_user_stats(
    current_user: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    total_users = db.query(UserDB).count()

    active_users = (
        db.query(UserDB)
        .filter(UserDB.is_active.is_(True))
        .count()
    )

    inactive_users = (
        db.query(UserDB)
        .filter(UserDB.is_active.is_(False))
        .count()
    )

    pharmacists = (
        db.query(UserDB)
        .filter(UserDB.role == "pharmacist")
        .count()
    )

    customers = (
        db.query(UserDB)
        .filter(UserDB.role == "customer")
        .count()
    )

    admins = (
        db.query(UserDB)
        .filter(UserDB.role == "admin")
        .count()
    )

    return {
        "total_users": total_users,
        "active_users": active_users,
        "inactive_users": inactive_users,
        "pharmacists": pharmacists,
        "customers": customers,
        "admins": admins,
    }


# ============================================================
# PHARMACIES
# ============================================================


@router.get("/pharmacies")
def list_admin_pharmacies(
    q: str | None = Query(
        default=None,
        max_length=100,
    ),
    active: bool | None = Query(
        default=None,
    ),
    skip: int = Query(
        default=0,
        ge=0,
    ),
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
    ),
    current_user: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = (
        db.query(OrganizationDB)
        .order_by(OrganizationDB.created_at.desc())
    )

    if q:
        search_term = q.strip()

        if search_term:
            pattern = f"%{search_term}%"

            query = query.filter(
                OrganizationDB.name.ilike(pattern)
                | OrganizationDB.slug.ilike(pattern)
            )

    if active is not None:
        query = query.filter(
            OrganizationDB.is_active == active
        )

    total = query.count()

    organizations = (
        query
        .offset(skip)
        .limit(limit)
        .all()
    )

    items = []

    for organization in organizations:
        pharmacist_count = sum(
            1
            for user in organization.users
            if user.role == "pharmacist"
            and user.is_active
        )

        customer_count = sum(
            1
            for customer in organization.customers
            if customer.is_active
        )

        prescription_count = len(
            organization.prescriptions
        )

        items.append(
            {
                "id": str(organization.id),
                "name": organization.name,
                "slug": organization.slug,
                "phone": organization.phone,
                "email": organization.email,
                "address": organization.address,
                "is_active": organization.is_active,
                "pharmacist_count": pharmacist_count,
                "customer_count": customer_count,
                "prescription_count": prescription_count,
                "created_at": (
                    organization.created_at.isoformat()
                    if organization.created_at
                    else None
                ),
            }
        )

    return {
        "items": items,
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/pharmacies/stats")
def get_admin_pharmacy_stats(
    current_user: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    total_pharmacies = (
        db.query(OrganizationDB)
        .count()
    )

    active_pharmacies = (
        db.query(OrganizationDB)
        .filter(
            OrganizationDB.is_active.is_(True)
        )
        .count()
    )

    inactive_pharmacies = (
        db.query(OrganizationDB)
        .filter(
            OrganizationDB.is_active.is_(False)
        )
        .count()
    )

    return {
        "total_pharmacies": total_pharmacies,
        "active_pharmacies": active_pharmacies,
        "inactive_pharmacies": inactive_pharmacies,
    }


# ============================================================
# PRESCRIPTION REVIEW QUEUE
# ============================================================


@router.get("/reviews")
def list_admin_reviews(
    q: str | None = Query(
        default=None,
        max_length=100,
        description="Search prescription ID, filename, or patient",
    ),
    review_status: str | None = Query(
        default=None,
        description="Review status filter",
    ),
    priority: str | None = Query(
        default=None,
        description="Priority filter",
    ),
    skip: int = Query(
        default=0,
        ge=0,
    ),
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
    ),
    current_user: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    allowed_statuses = {
        "pending",
        "under_review",
        "verified",
        "needs_clarification",
        "rejected",
    }

    if review_status and review_status not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail="Invalid review status.",
        )

    allowed_priorities = {
        "all",
        "high",
        "medium",
        "low",
    }

    if priority and priority not in allowed_priorities:
        raise HTTPException(
            status_code=400,
            detail="Invalid priority.",
        )

    query = (
        db.query(PrescriptionDB)
        .order_by(
            PrescriptionDB.created_at.desc()
        )
    )

    if review_status:
        query = query.filter(
            PrescriptionDB.review_status
            == review_status
        )

    prescriptions = query.all()

    search_term = (
        q.strip().lower()
        if q
        else ""
    )

    items = []

    for prescription in prescriptions:
        serialized = serialize_prescription(
            prescription
        )

        if search_term:
            organization_name = (
                serialized["organization"]["name"]
                if serialized["organization"]
                else ""
            )

            customer_name = (
                serialized["customer"]["name"]
                if serialized["customer"]
                else ""
            )

            haystack = " ".join(
                [
                    prescription.prescription_id
                    or "",
                    prescription.file_name
                    or "",
                    organization_name
                    or "",
                    customer_name
                    or "",
                ]
            ).lower()

            if search_term not in haystack:
                continue

        findings = serialized["findings"]

        if priority and priority != "all":
            if priority == "high":
                if (
                    findings["high"] == 0
                    and findings["critical"] == 0
                ):
                    continue

            elif priority == "medium":
                if findings["medium"] == 0:
                    continue

            elif priority == "low":
                if findings["total"] == 0:
                    continue

        items.append(
            serialized
        )

    # Highest-risk prescriptions first.
    def priority_rank(
        item: dict[str, Any],
    ) -> int:
        findings = item["findings"]

        if findings["critical"] > 0:
            return 0

        if findings["high"] > 0:
            return 1

        if findings["medium"] > 0:
            return 2

        if findings["low"] > 0:
            return 3

        return 4

    items.sort(
        key=lambda item: (
            priority_rank(item),
            item["review_status"],
            item["prescription_id"],
        )
    )

    total = len(items)

    paginated = items[
        skip : skip + limit
    ]

    return {
        "items": paginated,
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/reviews/stats")
def get_admin_review_stats(
    current_user: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    prescriptions = (
        db.query(PrescriptionDB)
        .all()
    )

    pending = 0
    under_review = 0
    verified = 0
    clarification = 0
    rejected = 0
    high_priority = 0

    for prescription in prescriptions:
        review_status = (
            prescription.review_status
            or "pending"
        )

        if review_status == "pending":
            pending += 1
        elif review_status == "under_review":
            under_review += 1
        elif review_status == "verified":
            verified += 1
        elif review_status == "needs_clarification":
            clarification += 1
        elif review_status == "rejected":
            rejected += 1

        if get_high_priority_findings(
            prescription
        ):
            high_priority += 1

    return {
        "total_reviews": len(prescriptions),
        "pending": pending,
        "under_review": under_review,
        "verified": verified,
        "needs_clarification": clarification,
        "rejected": rejected,
        "high_priority": high_priority,
    }


# ============================================================
# REVIEW DETAIL
# ============================================================


@router.get("/reviews/{prescription_id}")
def get_admin_review_detail(
    prescription_id: str,
    current_user: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
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
            status_code=404,
            detail="Prescription not found.",
        )

    data = serialize_prescription(
        prescription
    )

    audits = (
        db.query(ReviewAuditDB)
        .filter(
            ReviewAuditDB.prescription_id
            == prescription.id
        )
        .order_by(
            ReviewAuditDB.created_at.desc()
        )
        .all()
    )

    data["audit_history"] = [
        {
            "id": str(audit.id),
            "action": audit.action,
            "previous_status": audit.previous_status,
            "new_status": audit.new_status,
            "finding_type": audit.finding_type,
            "finding_data": audit.finding_data,
            "note": audit.note,
            "reviewer": (
                {
                    "id": str(audit.reviewer.id),
                    "name": audit.reviewer.name,
                    "email": audit.reviewer.email,
                    "role": audit.reviewer.role,
                }
                if audit.reviewer
                else None
            ),
            "created_at": (
                audit.created_at.isoformat()
                if audit.created_at
                else None
            ),
        }
        for audit in audits
    ]

    return data


# ============================================================
# ADMIN REVIEW ACTION
# ============================================================


@router.post(
    "/reviews/{prescription_id}/action"
)
def perform_admin_review_action(
    prescription_id: str,
    request: ReviewActionRequest,
    current_user: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Perform an administrator review action using the canonical
    prescription review validation and state-transition workflow.
    """

    from backend.routers.reviews import (
        determine_new_status,
        get_all_findings,
        get_finding_key,
        get_unresolved_high_priority_findings,
        validate_action,
        validate_finding,
    )

    validate_action(request.action)

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
            detail="Prescription not found.",
        )

    validate_finding(
        prescription,
        request,
    )

    previous_status = (
        prescription.review_status
        or "pending"
    )

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
            detail="Prescription is already verified.",
        )

    finding_index = (
        request.finding.finding_index
        if request.finding
        else None
    )

    new_status = determine_new_status(
        prescription,
        request.action,
        db,
        finding_index,
    )

    now = datetime.now(timezone.utc)

    finding_type = None
    finding_data = None

    if request.finding:
        finding_type = request.finding.finding_type

        finding_data = dict(
            request.finding.finding_data
        )

        if finding_index is not None:
            finding_data["finding_index"] = (
                finding_index
            )
            finding_data["finding_key"] = (
                get_finding_key(finding_index)
            )

    prescription.review_status = new_status

    if request.action != "start_review":
        prescription.reviewed_by_id = (
            current_user.id
        )
        prescription.reviewed_at = now

    if request.note:
        prescription.review_notes = request.note

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

    high_priority = (
        get_unresolved_high_priority_findings(
            prescription,
            db,
        )
    )

    total_findings = len(
        get_all_findings(prescription)
    )

    return {
        "prescription_id": (
            prescription.prescription_id
        ),
        "previous_status": previous_status,
        "review_status": (
            prescription.review_status
        ),
        "reviewed_by": {
            "id": str(current_user.id),
            "name": current_user.name,
            "email": current_user.email,
            "role": current_user.role,
        },
        "reviewed_by_id": (
            prescription.reviewed_by_id
        ),
        "reviewed_at": (
            prescription.reviewed_at.isoformat()
            if prescription.reviewed_at
            else None
        ),
        "review_notes": (
            prescription.review_notes
        ),
        "high_priority_findings": high_priority,
        "total_findings": total_findings,
        "action": request.action,
    }