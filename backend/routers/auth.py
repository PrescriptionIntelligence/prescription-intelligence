from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import (
    CustomerDB,
    OrganizationDB,
    UserDB,
)
from backend.schemas import (
    EmailVerificationResponse,
    ResendVerificationRequest,
    VerifyEmailRequest,
)
from backend.security import (
    create_access_token,
    generate_email_verification_token,
    hash_email_verification_token,
    hash_password,
    verify_email_verification_token,
    verify_password,
)
from backend.services.email_service import (
    send_email_verification,
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

    The account must verify its email before login.
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

    The account must verify its email before login.
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
    """
    Normalize email addresses consistently.
    """
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
        code = (
            f"{prefix}-"
            f"{secrets.randbelow(9000) + 1000}"
        )

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
            "is_active": user.is_active,
            "email_verified": user.email_verified,
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


def _create_verification_data() -> tuple[str, str, datetime]:
    """
    Create a raw verification token, its hash,
    and its expiration timestamp.
    """

    token = generate_email_verification_token()

    token_hash = hash_email_verification_token(
        token
    )

    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(minutes=30)
    )

    return (
        token,
        token_hash,
        expires_at,
    )

def _as_utc_datetime(value: datetime | None) -> datetime | None:
    """Normalize database timestamps to timezone-aware UTC."""
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)

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

    Pharmacists and customers MUST have verified
    email addresses before they can receive a JWT.

    Admin accounts are controlled separately and are
    not subject to public email registration.
    """

    normalized_email = _normalize_email(
        email
    )

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

    # -----------------------------------------------------
    # Mandatory email verification
    # -----------------------------------------------------

    if (
        user.role in {"pharmacist", "customer"}
        and not user.email_verified
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Email address is not verified. "
                "Please verify your email before signing in."
            ),
        )

    # -----------------------------------------------------
    # Create JWT only after all checks pass
    # -----------------------------------------------------

    token = create_access_token(
        user_id=str(user.id),
        role=user.role,
        organization_id=(
            str(user.organization_id)
            if user.organization_id
            else None
        ),
    )

    user.last_login_at = datetime.now(
        timezone.utc
    )

    db.commit()

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

    Flow:

        registration
            ↓
        unverified account
            ↓
        verification email
            ↓
        email verification
            ↓
        login

    No JWT is issued during registration.
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
    # Generate email verification credentials
    # -----------------------------------------------------

    (
        verification_token,
        verification_token_hash,
        verification_expires_at,
    ) = _create_verification_data()

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
        email_verified=False,
        email_verification_token_hash=(
            verification_token_hash
        ),
        email_verification_expires_at=(
            verification_expires_at
        ),
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
    # Send verification email
    # -----------------------------------------------------

    try:
        send_email_verification(
            recipient_email=user.email,
            recipient_name=user.name,
            verification_token=verification_token,
        )

        user.email_verification_sent_at = datetime.now(
            timezone.utc
        )
        db.commit()

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Your account was created, but the verification email "
                "could not be sent. Please use resend verification."
            ),
        )

    # -----------------------------------------------------
    # IMPORTANT:
    # No JWT is returned here.
    # -----------------------------------------------------

    return {
        "message": (
            "Account created successfully. "
            "Please verify your email before signing in."
        ),
        "email_verified": False,
        "user": {
            "id": str(user.id),
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "organization_id": str(
                user.organization_id
            ),
            "is_active": user.is_active,
        },
        "organization": {
            "id": str(organization.id),
            "name": organization.name,
            "slug": organization.slug,
        },
    }


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

    Customer accounts are global and can later be
    associated with multiple pharmacies.

    No JWT is issued until email verification.
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
    # Generate verification credentials
    # -----------------------------------------------------

    (
        verification_token,
        verification_token_hash,
        verification_expires_at,
    ) = _create_verification_data()

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
        email_verified=False,
        email_verification_token_hash=(
            verification_token_hash
        ),
        email_verification_expires_at=(
            verification_expires_at
        ),
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
    # Send verification email
    # -----------------------------------------------------

    try:
        send_email_verification(
            recipient_email=user.email,
            recipient_name=user.name,
            verification_token=verification_token,
        )

        user.email_verification_sent_at = datetime.now(
            timezone.utc
        )
        db.commit()

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Your account was created, but the verification email "
                "could not be sent. Please use resend verification."
            ),
        )

    # -----------------------------------------------------
    # IMPORTANT:
    # No JWT is returned here.
    # -----------------------------------------------------

    return {
        "message": (
            "Customer account created successfully. "
            "Please verify your email before signing in."
        ),
        "email_verified": False,
        "user": {
            "id": str(user.id),
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "organization_id": None,
            "is_active": user.is_active,
        },
        "customer": {
            "profile_linked": False,
            "customer_code": request.customer_code,
            "phone": request.phone,
        },
    }


# =========================================================
# VERIFY EMAIL
# =========================================================

@router.post(
    "/verify-email",
    response_model=EmailVerificationResponse,
)
def verify_email(
    request: VerifyEmailRequest,
    db: Session = Depends(get_db),
):
    """
    Verify ownership of an email address.

    The token is:
        - hashed in the database
        - time limited
        - invalidated after successful verification
    """

    normalized_email = _normalize_email(
        request.email
    )

    user = (
        db.query(UserDB)
        .filter(
            UserDB.email == normalized_email
        )
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification request",
        )

    if user.email_verified:
        return {
            "message": "Email address is already verified",
            "email_verified": True,
        }

    if not user.email_verification_token_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active verification request exists",
        )

    expires_at = (
        user.email_verification_expires_at
    )

    if not expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification request is invalid",
        )

    now = datetime.now(timezone.utc)

    # -----------------------------------------------------
    # Expiration
    # -----------------------------------------------------

    if expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Verification link has expired. "
                "Please request a new verification email."
            ),
        )

    # -----------------------------------------------------
    # Token validation
    # -----------------------------------------------------

    if not verify_email_verification_token(
        request.token,
        user.email_verification_token_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification token",
        )

    # -----------------------------------------------------
    # Mark verified
    # -----------------------------------------------------

    user.email_verified = True

    # One-time token:
    # remove it immediately after successful use.
    user.email_verification_token_hash = None
    user.email_verification_expires_at = None
    user.email_verification_sent_at = None

    db.commit()

    return {
        "message": "Email address verified successfully",
        "email_verified": True,
    }


# =========================================================
# RESEND VERIFICATION
# =========================================================

@router.post(
    "/resend-verification",
)
def resend_verification(
    request: ResendVerificationRequest,
    db: Session = Depends(get_db),
):
    """
    Generate and send a fresh verification token.

    Security properties:
        - generic response prevents account enumeration
        - 60-second database-backed resend cooldown
        - previous token is replaced
        - new token expires after 30 minutes
        - email is only marked as sent after successful delivery
    """

    RESEND_COOLDOWN_SECONDS = 60

    normalized_email = _normalize_email(
        request.email
    )

    generic_response = {
        "message": (
            "If an account exists for this email, "
            "a verification email has been sent."
        )
    }

    user = (
        db.query(UserDB)
        .filter(
            UserDB.email == normalized_email
        )
        .first()
    )

    # -----------------------------------------------------
    # Prevent account enumeration
    # -----------------------------------------------------

    if not user:
        return generic_response

    if user.email_verified:
        return {
            "message": "Email address is already verified."
        }

    # -----------------------------------------------------
    # Resend cooldown
    # -----------------------------------------------------

    now = datetime.now(timezone.utc)

    sent_at = _as_utc_datetime(
        user.email_verification_sent_at
    )

    if sent_at:
        elapsed = (
            now - sent_at
        ).total_seconds()

        if elapsed < RESEND_COOLDOWN_SECONDS:
            remaining = max(
                1,
                int(
                    RESEND_COOLDOWN_SECONDS
                    - elapsed
                ),
            )

            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    "Please wait before requesting "
                    "another verification email."
                ),
                headers={
                    "Retry-After": str(remaining),
                },
            )

    # -----------------------------------------------------
    # Generate fresh token
    # -----------------------------------------------------

    (
        verification_token,
        verification_token_hash,
        verification_expires_at,
    ) = _create_verification_data()

    user.email_verification_token_hash = (
        verification_token_hash
    )

    user.email_verification_expires_at = (
        verification_expires_at
    )

    # Commit the new token before sending.
    #
    # If sending fails, the account remains unverified
    # and the user can retry after the cooldown.
    db.commit()

    # -----------------------------------------------------
    # Send email
    # -----------------------------------------------------

    try:
        send_email_verification(
            recipient_email=user.email,
            recipient_name=user.name,
            verification_token=verification_token,
        )

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Unable to send the verification email. "
                "Please try again later."
            ),
        )

    # -----------------------------------------------------
    # Record successful email delivery attempt
    # -----------------------------------------------------

    user.email_verification_sent_at = now

    db.commit()

    return generic_response

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

    Pharmacist and customer accounts must have verified
    email addresses.
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