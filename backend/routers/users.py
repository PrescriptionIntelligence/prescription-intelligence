from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.auth import get_current_user, require_pharmacy_staff
from backend.database import get_db
from backend.models import CustomerDB, UserDB
from backend.services.customer_service import get_customer_by_user


router = APIRouter(
    prefix="/users",
    tags=["Users"],
)

@router.get(
    "/search",
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
            (
                CustomerDB.name.ilike(pattern)
                | CustomerDB.customer_code.ilike(pattern)
                | CustomerDB.phone.ilike(pattern)
                | CustomerDB.email.ilike(pattern)
            ),
        )
        .order_by(CustomerDB.name.asc())
        .limit(20)
        .all()
    )

    return customers

@router.get("/me")
def get_my_profile(
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return the authenticated user's profile.
    """

    organization = current_user.organization

    customer = None

    if current_user.role == "customer":
        customer = get_customer_by_user(
            current_user.id,
            db,
        )

    return {
        "id": str(current_user.id),
        "name": current_user.name,
        "email": current_user.email,
        "role": current_user.role,
        "is_active": current_user.is_active,
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
                "customer_code": customer.customer_code,
                "name": customer.name,
                "phone": customer.phone,
                "email": customer.email,
            }
            if customer
            else None
        ),
        "created_at": current_user.created_at,
        "last_login_at": current_user.last_login_at,
    }