from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
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
# SHARED AUTHENTICATION HELPER
# =========================================================

def _authenticate(email: str, password: str, db: Session) -> dict:
    """
    Verify credentials and return the token response dict.

    Raises HTTPException on invalid credentials or inactive account.
    Used by both the JSON login endpoint and the OAuth2 token endpoint.
    """

    user = (
        db.query(UserDB)
        .filter(UserDB.email == email.strip().lower())
        .first()
    )

    if not user or not verify_password(password, user.password_hash):
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
            str(user.organization_id) if user.organization_id else None
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
                str(user.organization_id) if user.organization_id else None
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
# LOGIN  (JSON body — used by the frontend application)
# =========================================================

@router.post("/login")
def login(
    request: LoginRequest,
    db: Session = Depends(get_db),
):
    """
    Authenticate with a JSON body containing ``email`` and ``password``.

    Used by the frontend application.
    Returns a full response including user and organization details.
    """
    return _authenticate(request.email, request.password, db)


# =========================================================
# TOKEN  (form-encoded — used by Swagger UI OAuth2 flow)
# =========================================================

@router.post(
    "/token",
    summary="OAuth2 token endpoint (Swagger Authorize)",
    description=(
        "OAuth2 password-flow token endpoint. "
        "Accepts ``username`` (your email) and ``password`` "
        "as ``application/x-www-form-urlencoded``. "
        "This is the endpoint wired to the Swagger Authorize button. "
        "For application use, prefer ``POST /auth/login`` with a JSON body."
    ),
)
def token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    OAuth2 password-flow token endpoint consumed by Swagger UI.

    The ``username`` field in the form maps to the user's email address.
    Returns ``access_token`` and ``token_type`` as required by the
    OAuth2 specification, plus the same extended fields as ``/auth/login``.
    """
    # OAuth2PasswordRequestForm uses `username`; this application uses email.
    return _authenticate(form_data.username, form_data.password, db)