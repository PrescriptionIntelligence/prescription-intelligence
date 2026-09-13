from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import CustomerDB, OrganizationDB, UserDB
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
    """
    Pharmacy registration.

    Creates:
        OrganizationDB
        UserDB(role="pharmacist")
    """

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


class CustomerRegisterRequest(BaseModel):
    """
    Customer self-registration.

    Customer accounts are not tied to one pharmacy.
    A customer can therefore have prescriptions from
    multiple pharmacies.
    """

    name: str = Field(
        min_length=2,
        max_length=200,
    )

    email: EmailStr

    password: str = Field(
        min_length=8,
        max_length=128,
    )

    phone: str | None = Field(
        default=None,
        max_length=30,
    )

    customer_code: str | None = Field(
        default=None,
        max_length=50,
    )


class LoginRequest(BaseModel):
    email: EmailStr

    password: str = Field(
        min_length=1,
        max_length=128,
    )


# =========================================================
# HELPERS
# =========================================================

def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _generate_unique_customer_code(
    name: str,
    db: Session,
) -> str:
    """
    Generate a unique internal customer code.

    Example:
        JOHN-4821
    """

    import secrets

    prefix = "".join(
        character
        for character in name.upper()
        if character.isalnum()
    )[:8]

    if not prefix:
        prefix = "CUSTOMER"

    for _ in range(20):
        code = f"{prefix}-{secrets.randbelow(9000) + 1000}"

        existing = (
            db.query(CustomerDB)
            .filter(
                CustomerDB.customer_code == code
            )
            .first()
        )

        if not existing:
            return code

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unable to generate a unique customer code",
    )


def _build_auth_response(
    user: UserDB,
    token: str,
    message: str,
) -> dict:
    """
    Build the common authentication response.
    """

    organization = user.organization

    return {
        "message": message,
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


# =========================================================
# SHARED AUTHENTICATION
# =========================================================

def _authenticate(
    email: str,
    password: str,
    db: Session,
) -> dict:
    """
    Authenticate pharmacist, customer, or admin.
    """

    normalized_email = _normalize_email(email)

    user = (
        db.query(UserDB)
        .filter(
            UserDB.email == normalized_email
        )
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    if not verify_password(
        password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    token = create_access_token(
        user_id=str(user.id),
        role=user.role,
        organization_id=(
            str(user.organization_id)
            if user.organization_id
            else None
        ),
    )

    return _build_auth_response(
        user=user,
        token=token,
        message="Login successful",
    )


# =========================================================
# PHARMACY REGISTRATION
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
    Register a new pharmacy and its first pharmacist.

    Public registration can only create a pharmacist account.

    Admin accounts are intentionally NOT created here.
    """

    normalized_email = _normalize_email(
        request.email
    )

    existing_user = (
        db.query(UserDB)
        .filter(
            UserDB.email == normalized_email
        )
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    # -----------------------------------------------------
    # Generate unique organization slug
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
        .filter(
            OrganizationDB.slug == slug
        )
        .first()
    ):
        slug = f"{base_slug}-{counter}"
        counter += 1

    # -----------------------------------------------------
    # Create pharmacy organization
    # -----------------------------------------------------

    organization = OrganizationDB(
        name=request.pharmacy_name.strip(),
        slug=slug,
    )

    db.add(organization)
    db.flush()

    # -----------------------------------------------------
    # Create pharmacist account
    # -----------------------------------------------------

    user = UserDB(
        organization_id=organization.id,
        name=request.name.strip(),
        email=normalized_email,
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
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create pharmacy account",
        )

    # -----------------------------------------------------
    # Login immediately after registration
    # -----------------------------------------------------

    token = create_access_token(
        user_id=str(user.id),
        role=user.role,
        organization_id=str(
            organization.id
        ),
    )

    return _build_auth_response(
        user=user,
        token=token,
        message="Account created successfully",
    )


# =========================================================
# CUSTOMER REGISTRATION
# =========================================================

@router.post(
    "/register/customer",
    status_code=status.HTTP_201_CREATED,
)
def register_customer(
    request: CustomerRegisterRequest,
    db: Session = Depends(get_db),
):
    """
    Register a customer account.

    IMPORTANT:
    A customer is not assigned to a single pharmacy.

    This allows the same customer to have prescriptions
    associated with Pharmacy A, Pharmacy B, Pharmacy C, etc.

    The CustomerDB organization_id is currently required by
    the existing database schema, so the customer UserDB
    account is created first.

    The CustomerDB profile will be linked when the customer
    is associated with a pharmacy/prescription.
    """

    normalized_email = _normalize_email(
        request.email
    )

    # -----------------------------------------------------
    # Prevent duplicate account
    # -----------------------------------------------------

    existing_user = (
        db.query(UserDB)
        .filter(
            UserDB.email == normalized_email
        )
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    # -----------------------------------------------------
    # Create customer UserDB account
    # -----------------------------------------------------

    user = UserDB(
        organization_id=None,
        name=request.name.strip(),
        email=normalized_email,
        password_hash=hash_password(
            request.password
        ),
        role="customer",
    )

    db.add(user)

    try:
        db.commit()
        db.refresh(user)

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create customer account",
        )

    # -----------------------------------------------------
    # Customer JWT
    # -----------------------------------------------------

    token = create_access_token(
        user_id=str(user.id),
        role="customer",
        organization_id=None,
    )

    response = _build_auth_response(
        user=user,
        token=token,
        message="Customer account created successfully",
    )

    # Customer-specific information for the frontend.
    response["customer"] = {
        "profile_linked": False,
        "customer_code": request.customer_code,
        "phone": request.phone,
    }

    return response


# =========================================================
# LOGIN
# =========================================================

@router.post("/login")
def login(
    request: LoginRequest,
    db: Session = Depends(get_db),
):
    """
    JSON login endpoint used by the frontend.

    Supports:

        pharmacist
        customer
        admin
    """

    return _authenticate(
        email=request.email,
        password=request.password,
        db=db,
    )


# =========================================================
# OAUTH2 TOKEN
# =========================================================

@router.post(
    "/token",
    summary="OAuth2 token endpoint (Swagger Authorize)",
    description=(
        "OAuth2 password-flow token endpoint. "
        "Accepts username (email) and password "
        "as application/x-www-form-urlencoded. "
        "Used by Swagger Authorize."
    ),
)
def token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    OAuth2 password-flow endpoint used by Swagger UI.

    username = user's email
    password = user's password
    """

    return _authenticate(
        email=form_data.username,
        password=form_data.password,
        db=db,
    )