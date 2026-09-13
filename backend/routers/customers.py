from __future__ import annotations

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
    PrescriptionDB,
    UserDB,
)
from backend.schemas import (
    CustomerCreateRequest,
    CustomerResponse,
    CustomerSearchResponse,
)
from backend.services.customer_service import (
    customer_belongs_to_organization,
    ensure_customer_organization_link,
    generate_customer_code,
    get_customer_by_user,
    get_customer_organizations,
)


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
# LINK CUSTOMER TO ANOTHER PHARMACY
# =========================================================

@router.post("/{customer_id}/link")
def link_customer_to_pharmacy(
    customer_id: UUID,
    current_user: UserDB = Depends(require_pharmacy_staff),
    db: Session = Depends(get_db),
):
    organization = current_user.organization

    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pharmacy organization is required",
        )

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

    already_linked = customer_belongs_to_organization(
        customer.id,
        organization.id,
        db,
    )

    if not already_linked:
        ensure_customer_organization_link(
            customer=customer,
            organization=organization,
            db=db,
        )
        db.commit()

    return {
        "message": (
            "Customer is already linked to this pharmacy"
            if already_linked
            else "Customer linked to pharmacy successfully"
        ),
        "customer": {
            "id": str(customer.id),
            "customer_code": customer.customer_code,
            "name": customer.name,
        },
        "pharmacy": {
            "id": str(organization.id),
            "name": organization.name,
            "slug": organization.slug,
        },
        "already_linked": already_linked,
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