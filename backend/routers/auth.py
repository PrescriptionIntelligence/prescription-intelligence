from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import OrganizationDB, UserDB
from backend.security import (
    create_access_token,
    hash_password,
    verify_password,
)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


# =========================================================
# SCHEMAS
# =========================================================

class RegisterRequest(BaseModel):
    name: str = Field(
        min_length=2,
        max_length=200,
    )

    email: EmailStr

    password: str = Field(
        min_length=8,
        max_length=128,
    )

    pharmacy_name: str = Field(
        min_length=2,
        max_length=200,
    )


class LoginRequest(BaseModel):
    email: EmailStr

    password: str = Field(
        min_length=1,
        max_length=128,
    )


# =========================================================
# REGISTER
# =========================================================

@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
)
def register(
    request: RegisterRequest,
    db: Session = Depends(get_db),
):
    """
    Register a new pharmacist and create their pharmacy
    organization.

    The first user of an organization becomes its pharmacist.
    """

    existing_user = (
        db.query(UserDB)
        .filter(
            UserDB.email == request.email.lower()
        )
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    # -----------------------------------------------------
    # Generate organization slug
    # -----------------------------------------------------

    base_slug = (
        request.pharmacy_name
        .strip()
        .lower()
        .replace(" ", "-")
    )

    slug = base_slug
    counter = 2

    while (
        db.query(OrganizationDB)
        .filter(OrganizationDB.slug == slug)
        .first()
    ):
        slug = f"{base_slug}-{counter}"
        counter += 1

    # -----------------------------------------------------
    # Create organization
    # -----------------------------------------------------

    organization = OrganizationDB(
        name=request.pharmacy_name.strip(),
        slug=slug,
    )

    db.add(organization)
    db.flush()

    # -----------------------------------------------------
    # Create pharmacist
    # -----------------------------------------------------

    user = UserDB(
        organization_id=organization.id,
        name=request.name.strip(),
        email=request.email.lower(),
        password_hash=hash_password(
            request.password
        ),
        role="pharmacist",
    )

    db.add(user)

    try:
        db.commit()
        db.refresh(user)
        db.refresh(organization)

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Failed to create account",
        )

    token = create_access_token(
        user_id=str(user.id),
        role=user.role,
        organization_id=str(
            organization.id
        ),
    )

    return {
        "message": "Account created successfully",
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "organization_id": str(
                organization.id
            ),
        },
        "organization": {
            "id": str(organization.id),
            "name": organization.name,
            "slug": organization.slug,
        },
    }


# =========================================================
# LOGIN
# =========================================================

@router.post("/login")
def login(
    request: LoginRequest,
    db: Session = Depends(get_db),
):
    """
    Authenticate a pharmacist or administrator.
    """

    user = (
        db.query(UserDB)
        .filter(
            UserDB.email == request.email.lower()
        )
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not verify_password(
        request.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    organization = user.organization

    token = create_access_token(
        user_id=str(user.id),
        role=user.role,
        organization_id=(
            str(user.organization_id)
            if user.organization_id
            else None
        ),
    )

    return {
        "message": "Login successful",
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "organization_id": (
                str(user.organization_id)
                if user.organization_id
                else None
            ),
        },
        "organization": (
            {
                "id": str(organization.id),
                "name": organization.name,
                "slug": organization.slug,
            }
            if organization
            else None
        ),
    }