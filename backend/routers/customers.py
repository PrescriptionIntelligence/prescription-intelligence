from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, selectinload

from backend.auth import (
    require_any_authenticated_user,
    require_pharmacy_staff,
)
from backend.database import get_db
from backend.models import (
    CustomerDB,
    CustomerPharmacyLinkRequestDB,
    PrescriptionDB,
    UserDB,
)
from backend.schemas import (
    CustomerCreateRequest,
    CustomerResponse,
    CustomerSearchResponse,
    PharmacyLinkAcceptRequest,
    PharmacyLinkRequestResponse,
)
from backend.services.customer_service import (
    customer_belongs_to_organization,
    ensure_customer_organization_link,
    generate_customer_code,
    get_customer_by_user,
    get_customer_organizations,
)

_LINK_TOKEN_EXPIRY_HOURS = 72


router = APIRouter(prefix="/customers", tags=["Customers"])


# =========================================================
# PHARMACY CUSTOMER CREATION
# =========================================================

@router.post(
    "",
    response_model=CustomerResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_customer(
    request: CustomerCreateRequest,
    current_user: UserDB = Depends(require_pharmacy_staff),
    db: Session = Depends(get_db),
):
    organization = current_user.organization

    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pharmacy organization is required",
        )

    name = request.name.strip()

    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Customer name cannot be empty",
        )

    customer = CustomerDB(
        organization_id=organization.id,
        customer_code=generate_customer_code(name, db),
        name=name,
        phone=request.phone.strip() if request.phone else None,
        email=request.email.strip().lower() if request.email else None,
        date_of_birth=request.date_of_birth,
        address=request.address.strip() if request.address else None,
        notes=request.notes.strip() if request.notes else None,
        is_active=True,
    )

    db.add(customer)
    db.flush()

    # The original organization_id remains the customer's
    # primary/legacy organization. The membership table is
    # the source of truth for additional pharmacy links.
    ensure_customer_organization_link(
        customer=customer,
        organization=organization,
        db=db,
    )

    db.commit()
    db.refresh(customer)

    return customer


# =========================================================
# PHARMACY CUSTOMER LIST
# =========================================================

@router.get("")
def list_customers(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: UserDB = Depends(require_pharmacy_staff),
    db: Session = Depends(get_db),
):
    organization = current_user.organization

    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pharmacy organization is required",
        )

    customers = (
        db.query(CustomerDB)
        .filter(
            CustomerDB.organization_id == organization.id,
        )
        .order_by(CustomerDB.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return [
        {
            "id": str(customer.id),
            "customer_code": customer.customer_code,
            "name": customer.name,
            "phone": customer.phone,
            "email": customer.email,
            "date_of_birth": customer.date_of_birth,
            "address": customer.address,
            "notes": customer.notes,
            "is_active": customer.is_active,
            "created_at": customer.created_at,
            "updated_at": customer.updated_at,
        }
        for customer in customers
    ]


# =========================================================
# PHARMACY CUSTOMER SEARCH
# =========================================================

@router.get(
    "/search",
    response_model=list[CustomerSearchResponse],
)
def search_customers(
    q: str = Query(min_length=1, max_length=100),
    current_user: UserDB = Depends(require_pharmacy_staff),
    db: Session = Depends(get_db),
):
    organization = current_user.organization

    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pharmacy organization is required",
        )

    search_term = q.strip()

    if not search_term:
        return []

    pattern = f"%{search_term}%"

    customers = (
        db.query(CustomerDB)
        .filter(
            CustomerDB.organization_id == organization.id,
            CustomerDB.is_active.is_(True),
        )
        .filter(
            (CustomerDB.name.ilike(pattern))
            | (CustomerDB.customer_code.ilike(pattern))
            | (CustomerDB.phone.ilike(pattern))
            | (CustomerDB.email.ilike(pattern))
        )
        .order_by(CustomerDB.name.asc())
        .limit(20)
        .all()
    )

    return customers


# =========================================================
# CURRENT CUSTOMER PROFILE
# =========================================================

@router.get("/me")
def get_my_customer_profile(
    current_user: UserDB = Depends(require_any_authenticated_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "customer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customer account required",
        )

    customer = get_customer_by_user(current_user.id, db)

    if customer is None:
        return {
            "profile_linked": False,
            "customer": None,
        }

    organizations = get_customer_organizations(
        customer.id,
        db,
    )

    return {
        "profile_linked": True,
        "customer": {
            "id": str(customer.id),
            "customer_code": customer.customer_code,
            "name": customer.name,
            "phone": customer.phone,
            "email": customer.email,
            "date_of_birth": customer.date_of_birth,
            "address": customer.address,
            "notes": customer.notes,
            "is_active": customer.is_active,
            "created_at": customer.created_at,
            "updated_at": customer.updated_at,
        },
        "pharmacies": [
            {
                "id": str(organization.id),
                "name": organization.name,
                "slug": organization.slug,
            }
            for organization in organizations
        ],
    }


# =========================================================
# CURRENT CUSTOMER PHARMACIES
# =========================================================

@router.get("/me/pharmacies")
def get_my_pharmacies(
    current_user: UserDB = Depends(require_any_authenticated_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "customer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customer account required",
        )

    customer = get_customer_by_user(current_user.id, db)

    if customer is None:
        return []

    organizations = get_customer_organizations(
        customer.id,
        db,
    )

    return [
        {
            "id": str(organization.id),
            "name": organization.name,
            "slug": organization.slug,
        }
        for organization in organizations
    ]


# =========================================================
# CURRENT CUSTOMER PRESCRIPTION HISTORY
# =========================================================

@router.get("/me/prescriptions")
def get_my_prescriptions(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: UserDB = Depends(require_any_authenticated_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "customer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customer account required",
        )

    customer = get_customer_by_user(
        current_user.id,
        db,
    )

    if customer is None:
        return []

    prescriptions = (
        db.query(PrescriptionDB)
        .options(
            selectinload(
                PrescriptionDB.medicines
            )
        )
        .filter(
            PrescriptionDB.customer_id == customer.id
        )
        .order_by(
            PrescriptionDB.created_at.desc()
        )
        .offset(skip)
        .limit(limit)
        .all()
    )

    return prescriptions


# =========================================================
# LINK CUSTOMER TO ANOTHER PHARMACY (creates pending request)
# =========================================================

@router.post(
    "/{customer_id}/link",
    response_model=PharmacyLinkRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_customer_pharmacy_link(
    customer_id: UUID,
    current_user: UserDB = Depends(require_pharmacy_staff),
    db: Session = Depends(get_db),
):
    """
    Create a pending customer-pharmacy link request.

    The pharmacist initiates the request; NO membership is
    created at this point.  The customer must call
    POST /customers/me/pharmacy-link/accept with the returned
    token to consent and complete the link.

    Returns HTTP 202 with the one-time token the pharmacist
    (or the platform) must deliver to the customer.
    """

    organization = current_user.organization

    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pharmacy organization is required",
        )

    # Scope lookup to customers already within this pharmacist's
    # organization so a pharmacist cannot enumerate global UUIDs.
    customer = (
        db.query(CustomerDB)
        .filter(
            CustomerDB.id == customer_id,
            CustomerDB.organization_id == organization.id,
        )
        .first()
    )

    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    # If already linked, return a clear message without creating
    # a duplicate request.
    if customer_belongs_to_organization(
        customer.id,
        organization.id,
        db,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Customer is already linked to this pharmacy",
        )

    # Generate a cryptographically-random one-time token.
    raw_token = secrets.token_hex(32)  # 256-bit
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(
        hours=_LINK_TOKEN_EXPIRY_HOURS
    )

    link_request = CustomerPharmacyLinkRequestDB(
        customer_id=customer.id,
        organization_id=organization.id,
        token_hash=token_hash,
        status="pending",
        expires_at=expires_at,
    )

    db.add(link_request)
    db.commit()
    db.refresh(link_request)

    return PharmacyLinkRequestResponse(
        message=(
            "Link request created. "
            "Deliver the token to the customer for consent."
        ),
        request_id=link_request.id,
        customer_id=customer.id,
        organization_id=organization.id,
        token=raw_token,
        expires_at=expires_at,
    )


# =========================================================
# CUSTOMER ACCEPTS PHARMACY LINK REQUEST
# =========================================================

@router.post(
    "/me/pharmacy-link/accept",
    status_code=status.HTTP_200_OK,
)
def accept_pharmacy_link_request(
    body: PharmacyLinkAcceptRequest,
    current_user: UserDB = Depends(require_any_authenticated_user),
    db: Session = Depends(get_db),
):
    """
    Authenticated customer accepts a pending pharmacy-link request.

    The customer submits the raw token they received.  The backend:
      1. Hashes the token and looks up the request.
      2. Verifies the request belongs to this customer's profile.
      3. Checks the request is still pending and not expired.
      4. Creates CustomerOrganizationDB membership.
      5. Marks the request as accepted (one-time use).
    """

    if current_user.role != "customer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customer account required",
        )

    customer = get_customer_by_user(current_user.id, db)

    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer profile not found",
        )

    token_hash = hashlib.sha256(
        body.token.encode()
    ).hexdigest()

    link_request = (
        db.query(CustomerPharmacyLinkRequestDB)
        .filter(
            CustomerPharmacyLinkRequestDB.token_hash == token_hash
        )
        .first()
    )

    # Deliberately generic error: do not reveal whether the token
    # exists, belongs to another customer, or is expired.
    _invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid or expired link token",
    )

    if link_request is None:
        raise _invalid

    # Case G — cross-customer manipulation
    if link_request.customer_id != customer.id:
        raise _invalid

    # Case D/E — expired or already used
    if link_request.status != "pending":
        raise _invalid

    now = datetime.now(timezone.utc)

    # Normalize expires_at to UTC-aware for comparison; SQLite
    # returns naive datetimes while PostgreSQL returns aware ones.
    expires_at = link_request.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < now:
        link_request.status = "expired"
        db.commit()
        raise _invalid

    # Load the organization name before commit to avoid
    # a post-commit lazy-load on an expired instance.
    organization = link_request.organization
    org_id = link_request.organization_id
    org_name = organization.name

    # Case F — duplicate membership is handled idempotently by
    # ensure_customer_organization_link (no duplicate insert).
    ensure_customer_organization_link(
        customer=customer,
        organization=organization,
        db=db,
    )

    link_request.status = "accepted"
    link_request.accepted_at = now

    db.commit()

    return {
        "message": "Pharmacy linked successfully",
        "organization_id": str(org_id),
        "organization_name": org_name,
    }


# =========================================================
# PHARMACY CUSTOMER DETAIL
# =========================================================

@router.get("/{customer_id}")
def get_customer(
    customer_id: UUID,
    current_user: UserDB = Depends(require_pharmacy_staff),
    db: Session = Depends(get_db),
):
    customer = (
        db.query(CustomerDB)
        .options(
            selectinload(
                CustomerDB.organization_memberships
            )
        )
        .filter(CustomerDB.id == customer_id)
        .first()
    )

    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    organization = current_user.organization

    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Pharmacy organization is required",
        )

    # A pharmacist can only view a customer linked to
    # their pharmacy.
    if not customer_belongs_to_organization(
        customer.id,
        organization.id,
        db,
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    organizations = get_customer_organizations(
        customer.id,
        db,
    )

    prescription_count = (
        db.query(PrescriptionDB)
        .filter(
            PrescriptionDB.customer_id == customer.id
        )
        .count()
    )

    return {
        "id": str(customer.id),
        "customer_code": customer.customer_code,
        "name": customer.name,
        "phone": customer.phone,
        "email": customer.email,
        "date_of_birth": customer.date_of_birth,
        "address": customer.address,
        "notes": customer.notes,
        "is_active": customer.is_active,
        "organization_id": str(customer.organization_id),
        "created_at": customer.created_at,
        "updated_at": customer.updated_at,
        "prescription_count": prescription_count,
        "pharmacies": [
            {
                "id": str(organization.id),
                "name": organization.name,
                "slug": organization.slug,
            }
            for organization in organizations
        ],
    }


# =========================================================
# CUSTOMER PRESCRIPTION HISTORY FOR PHARMACY
# =========================================================

@router.get("/{customer_id}/prescriptions")
def get_customer_prescriptions(
    customer_id: UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: UserDB = Depends(require_pharmacy_staff),
    db: Session = Depends(get_db),
):
    customer = (
        db.query(CustomerDB)
        .filter(CustomerDB.id == customer_id)
        .first()
    )

    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    organization = current_user.organization

    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Pharmacy organization is required",
        )

    # Membership is required before a pharmacist can
    # access this customer's prescription history.
    if not customer_belongs_to_organization(
        customer.id,
        organization.id,
        db,
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    prescriptions = (
        db.query(PrescriptionDB)
        .options(
            selectinload(
                PrescriptionDB.medicines
            )
        )
        .filter(
            PrescriptionDB.customer_id == customer.id,
            PrescriptionDB.organization_id == organization.id,
        )
        .order_by(
            PrescriptionDB.created_at.desc()
        )
        .offset(skip)
        .limit(limit)
        .all()
    )

    return prescriptions