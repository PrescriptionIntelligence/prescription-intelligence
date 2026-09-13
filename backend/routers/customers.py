from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from backend.auth import (
    require_any_authenticated_user,
    require_pharmacy_staff,
)
from backend.services.customer_service import (
    customer_belongs_to_organization,
    get_customer_by_user,
    get_customer_organizations,
    get_or_create_customer_profile,
)
from backend.database import get_db
from backend.models import (
    CustomerDB,
    CustomerOrganizationDB,
    OrganizationDB,
    PrescriptionDB,
    UserDB,
)


router = APIRouter(
    prefix="/customers",
    tags=["Customers"],
)


# =========================================================
# PHARMACY CUSTOMER LIST
# =========================================================


@router.get("")
def list_customers(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: UserDB = Depends(
        require_pharmacy_staff
    ),
    db: Session = Depends(get_db),
):
    """
    List customers belonging to the pharmacist's pharmacy.

    Admins can see all customers.
    Pharmacists can only see customers linked to
    their own organization.
    """

    if current_user.role == "admin":
        query = db.query(CustomerDB)

    else:
        if not current_user.organization_id:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Pharmacist is not associated "
                    "with an organization"
                ),
            )

        query = (
            db.query(CustomerDB)
            .join(
                CustomerOrganizationDB,
                CustomerOrganizationDB.customer_id
                == CustomerDB.id,
            )
            .filter(
                CustomerOrganizationDB.organization_id
                == current_user.organization_id
            )
        )

    customers = (
        query
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
            "date_of_birth": (
                customer.date_of_birth
                if customer.date_of_birth
                else None
            ),
            "address": customer.address,
            "notes": customer.notes,
            "is_active": customer.is_active,
            "created_at": customer.created_at,
            "updated_at": customer.updated_at,
        }
        for customer in customers
    ]


# =========================================================
# CURRENT CUSTOMER PROFILE
# =========================================================


@router.get("/me")
def get_my_customer_profile(
    current_user: UserDB = Depends(
        require_any_authenticated_user
    ),
    db: Session = Depends(get_db),
):
    """
    Return the authenticated customer's profile.

    Only users with role=customer can access this endpoint.
    """

    if current_user.role != "customer":
        raise HTTPException(
            status_code=403,
            detail="Customer access required",
        )

    customer = get_customer_by_user(
        current_user.id,
        db,
    )

    if not customer:
        raise HTTPException(
            status_code=404,
            detail="Customer profile not found",
        )

    organizations = get_customer_organizations(
        customer.id,
        db,
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
        "created_at": customer.created_at,
        "updated_at": customer.updated_at,
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
    current_user: UserDB = Depends(
        require_any_authenticated_user
    ),
    db: Session = Depends(get_db),
):
    """
    Return all pharmacies linked to the authenticated customer.
    """

    if current_user.role != "customer":
        raise HTTPException(
            status_code=403,
            detail="Customer access required",
        )

    customer = get_customer_by_user(
        current_user.id,
        db,
    )

    if not customer:
        raise HTTPException(
            status_code=404,
            detail="Customer profile not found",
        )

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
# CURRENT CUSTOMER PRESCRIPTIONS
# =========================================================


@router.get("/me/prescriptions")
def get_my_prescriptions(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: UserDB = Depends(
        require_any_authenticated_user
    ),
    db: Session = Depends(get_db),
):
    """
    Return all prescriptions belonging to the authenticated
    customer's profile.
    """

    if current_user.role != "customer":
        raise HTTPException(
            status_code=403,
            detail="Customer access required",
        )

    customer = get_customer_by_user(
        current_user.id,
        db,
    )

    if not customer:
        return []

    prescriptions = (
        db.query(PrescriptionDB)
        .options(
            selectinload(
                PrescriptionDB.medicines
            )
        )
        .filter(
            PrescriptionDB.customer_id
            == customer.id
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
# PHARMACY CUSTOMER DETAIL
# =========================================================


@router.get("/{customer_id}")
def get_customer(
    customer_id: UUID,
    current_user: UserDB = Depends(
        require_pharmacy_staff
    ),
    db: Session = Depends(get_db),
):
    """
    Return one customer.

    Pharmacists can only access customers linked to
    their organization.

    Admins can access any customer.
    """

    customer = (
        db.query(CustomerDB)
        .filter(
            CustomerDB.id == customer_id
        )
        .first()
    )

    if not customer:
        raise HTTPException(
            status_code=404,
            detail="Customer not found",
        )

    if current_user.role != "admin":
        if not current_user.organization_id:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Pharmacist is not associated "
                    "with an organization"
                ),
            )

        if not customer_belongs_to_organization(
            customer.id,
            current_user.organization_id,
            db,
        ):
            raise HTTPException(
                status_code=404,
                detail="Customer not found",
            )

    organizations = get_customer_organizations(
        customer.id,
        db,
    )

    prescription_count = (
        db.query(PrescriptionDB)
        .filter(
            PrescriptionDB.customer_id
            == customer.id
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
    current_user: UserDB = Depends(
        require_pharmacy_staff
    ),
    db: Session = Depends(get_db),
):
    """
    Return prescriptions for a customer.

    Pharmacists can only retrieve prescriptions belonging
    to the customer AND their own pharmacy organization.

    Admins can retrieve all prescriptions for the customer.
    """

    customer = (
        db.query(CustomerDB)
        .filter(
            CustomerDB.id == customer_id
        )
        .first()
    )

    if not customer:
        raise HTTPException(
            status_code=404,
            detail="Customer not found",
        )

    query = (
        db.query(PrescriptionDB)
        .options(
            selectinload(
                PrescriptionDB.medicines
            )
        )
        .filter(
            PrescriptionDB.customer_id
            == customer.id
        )
    )

    if current_user.role != "admin":
        if not current_user.organization_id:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Pharmacist is not associated "
                    "with an organization"
                ),
            )

        if not customer_belongs_to_organization(
            customer.id,
            current_user.organization_id,
            db,
        ):
            raise HTTPException(
                status_code=404,
                detail="Customer not found",
            )

        query = query.filter(
            PrescriptionDB.organization_id
            == current_user.organization_id
        )

    prescriptions = (
        query
        .order_by(
            PrescriptionDB.created_at.desc()
        )
        .offset(skip)
        .limit(limit)
        .all()
    )

    return prescriptions