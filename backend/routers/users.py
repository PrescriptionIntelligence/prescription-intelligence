from fastapi import APIRouter, Depends

from backend.auth import get_current_user
from backend.models import UserDB


router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


@router.get("/me")
def get_my_profile(
    current_user: UserDB = Depends(get_current_user),
):
    """
    Return the authenticated user's profile.
    """

    organization = current_user.organization

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
        "created_at": current_user.created_at,
        "last_login_at": current_user.last_login_at,
    }