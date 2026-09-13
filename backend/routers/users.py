from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.services.customer_service import get_customer_by_user
from backend.database import get_db
from backend.models import UserDB


router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


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