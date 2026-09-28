from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.rate_limit import limiter
from backend.models import (
    CustomerDB,
    OrganizationDB,
    PasswordResetTokenDB,
    RevokedAccessTokenDB,
    UserDB,
)
from backend.schemas import (
    EmailVerificationResponse,
    ForgotPasswordRequest,
    PasswordResetResponse,
    ResendVerificationRequest,
    ResetPasswordRequest,
    VerifyEmailRequest,
)
from backend.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ALGORITHM,
    COOKIE_MAX_AGE,
    COOKIE_NAME,
    COOKIE_SECURE,
    SECRET_KEY,
    create_access_token,
    decode_access_token,
    generate_email_verification_token,
    generate_password_reset_token,
    hash_email_verification_token,
    hash_password,
    hash_password_reset_token,
    PASSWORD_RESET_EXPIRE_MINUTES,
    verify_email_verification_token,
    verify_password,
    verify_password_reset_token,
)
from backend.services.email_service import (
    send_email_verification,
    send_password_reset_email,
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
    Build the common authentication response body.
    access_token is kept in the JSON response for Swagger/Bearer
    compatibility.  The caller is responsible for also setting
    the HttpOnly cookie.
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


def _set_auth_cookie(response: Response, token: str) -> None:
    """
    Attach the HttpOnly session cookie to an existing response.
    """
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
        max_age=COOKIE_MAX_AGE,
    )


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
) -> tuple[dict, str]:
    """
    Authenticate pharmacist, customer, or admin.

    Pharmacists and customers MUST have verified
    email addresses before they can receive a JWT.

    Admin accounts are controlled separately and are
    not subject to public email registration.

    Returns (response_body, raw_jwt_token) so callers can
    attach the cookie and return the JSON body separately.
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

    return (
        _build_auth_response(
            user=user,
            token=token,
            message="Login successful",
        ),
        token,
    )


# =========================================================
# PHARMACY REGISTRATION
# =========================================================

@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("5/minute")
def register(
    body: RegisterRequest,
    request: Request,
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
        body.email
    )

    # -----------------------------------------------------
    # Prevent duplicate account — generic response to avoid
    # email enumeration (P7.12-A).
    # -----------------------------------------------------

    existing_user = (
        db.query(UserDB)
        .filter(
            UserDB.email == normalized_email
        )
        .first()
    )

    if existing_user:
        return {
            "message": (
                "If this email is not already registered, "
                "your account has been created. "
                "Please check your inbox to verify your email."
            )
        }

    # -----------------------------------------------------
    # Generate unique organization slug
    # -----------------------------------------------------

    base_slug = (
        body.pharmacy_name
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
        name=body.pharmacy_name.strip(),
        slug=slug,
    )

    db.add(organization)
    db.flush()

    # -----------------------------------------------------
    # Create pharmacist account
    # -----------------------------------------------------

    user = UserDB(
        organization_id=organization.id,
        name=body.name.strip(),
        email=normalized_email,
        password_hash=hash_password(
            body.password
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
@limiter.limit("5/minute")
def register_customer(
    body: CustomerRegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Register a customer account.

    Customer accounts are global and can later be
    associated with multiple pharmacies.

    No JWT is issued until email verification.
    """

    normalized_email = _normalize_email(
        body.email
    )

    # -----------------------------------------------------
    # Prevent duplicate account — generic response to avoid
    # email enumeration (P7.12-A).
    # -----------------------------------------------------

    existing_user = (
        db.query(UserDB)
        .filter(
            UserDB.email == normalized_email
        )
        .first()
    )

    if existing_user:
        return {
            "message": (
                "If this email is not already registered, "
                "your account has been created. "
                "Please check your inbox to verify your email."
            )
        }

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
        name=body.name.strip(),
        email=normalized_email,
        password_hash=hash_password(
            body.password
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
            "customer_code": body.customer_code,
            "phone": body.phone,
        },
    }


# =========================================================
# VERIFY EMAIL
# =========================================================

@router.post(
    "/verify-email",
    response_model=EmailVerificationResponse,
)
@limiter.limit("10/minute")
def verify_email(
    body: VerifyEmailRequest,
    request: Request,
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
        body.email
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
        body.token,
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
@limiter.limit("5/minute")
def resend_verification(
    body: ResendVerificationRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Generate and send a fresh verification token.

    Security properties:
        - generic response prevents account enumeration
        - invited-pharmacist accounts are detected and protected:
          their invitation token is never overwritten by this endpoint
        - 60-second database-backed resend cooldown
        - previous token is replaced
        - new token expires after 30 minutes
        - email is only marked as sent after successful delivery
    """

    RESEND_COOLDOWN_SECONDS = 60

    normalized_email = _normalize_email(
        body.email
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

    # -----------------------------------------------------
    # Invited-pharmacist guard
    #
    # An invited pharmacist has is_active=False,
    # email_verified=False, and a 72-hour invitation token.
    # Replacing that token here would silently destroy the
    # invite flow.  Return a specific message so the invitee
    # knows what to do, but do NOT confirm email existence
    # to unauthenticated callers who do not already know.
    # -----------------------------------------------------

    if (
        not user.is_active
        and user.role == "pharmacist"
        and not user.email_verified
    ):
        return {
            "message": (
                "This account is awaiting invitation acceptance. "
                "Please use the original invitation email or ask "
                "the inviting pharmacist to send a new invitation."
            )
        }

    if user.email_verified:
        return generic_response

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
@limiter.limit("10/minute")
def login(
    body: LoginRequest,
    request: Request,
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

    On success:
        - Returns JSON body including access_token (Bearer compat)
        - Sets HttpOnly pi_access_token cookie (browser auth)
    """

    body_data, token = _authenticate(
        email=body.email,
        password=body.password,
        db=db,
    )

    response = JSONResponse(content=body_data)
    _set_auth_cookie(response, token)
    return response


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
@limiter.limit("10/minute")
def token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    OAuth2 password-flow endpoint used by Swagger UI.

    username = user's email
    password = user's password

    Also sets the HttpOnly cookie so Swagger users automatically
    benefit from cookie authentication after authorization.
    """

    body_data, raw_token = _authenticate(
        email=form_data.username,
        password=form_data.password,
        db=db,
    )

    response = JSONResponse(content=body_data)
    _set_auth_cookie(response, raw_token)
    return response


# =========================================================
# LOGOUT
# =========================================================

# Reuse the same bearer extractor that get_current_user uses,
# but with auto_error=False so unauthenticated logout is safe.
_logout_bearer = OAuth2PasswordBearer(
    tokenUrl="/auth/token",
    auto_error=False,
)


@router.post("/logout")
def logout(
    response: Response,
    bearer_token: Optional[str] = Depends(_logout_bearer),
    cookie_token: Optional[str] = Cookie(
        default=None, alias=COOKIE_NAME
    ),
    db: Session = Depends(get_db),
):
    """
    Revoke the current JWT and clear the HttpOnly session cookie.

    Per-token revocation via jti denylist:
        - Extracts the JWT from cookie (preferred) or Bearer header.
        - Adds the jti to revoked_access_tokens so the same token
          cannot be replayed via either cookie or Bearer transport.
        - Clears the browser cookie.
        - Other sessions (different jti) remain valid.

    If no token is present (already-expired cookie, no auth header)
    the cookie is still cleared and 200 is returned.  Logout must
    never fail for the user.

    The raw JWT is NOT stored — only the jti identifier.
    """
    # Cookie preferred, fall back to Bearer (same priority as get_current_user).
    token = cookie_token or bearer_token

    if token:
        try:
            payload = decode_access_token(token)
            jti = payload.get("jti")
            user_id_str = payload.get("sub")

            if jti and user_id_str:
                from uuid import UUID as _UUID
                try:
                    user_uuid = _UUID(user_id_str)
                except (ValueError, AttributeError):
                    user_uuid = None

                if user_uuid:
                    # Determine token exp for denylist row lifetime.
                    exp = payload.get("exp")
                    if exp:
                        from datetime import datetime as _dt, timezone as _tz, timedelta as _td
                        try:
                            expires_at = _dt.fromtimestamp(int(exp), tz=_tz.utc)
                        except (TypeError, ValueError, OverflowError):
                            expires_at = (
                                _dt.now(_tz.utc)
                                + _td(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
                            )
                    else:
                        from datetime import datetime as _dt, timezone as _tz, timedelta as _td
                        expires_at = (
                            _dt.now(_tz.utc)
                            + _td(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
                        )

                    # Idempotent: only insert if not already revoked.
                    existing = (
                        db.query(RevokedAccessTokenDB)
                        .filter(RevokedAccessTokenDB.jti == jti)
                        .first()
                    )
                    if not existing:
                        revoked = RevokedAccessTokenDB(
                            jti=jti,
                            user_id=user_uuid,
                            expires_at=expires_at,
                        )
                        db.add(revoked)
                        try:
                            db.commit()
                        except Exception:
                            db.rollback()
                            # Non-fatal: cookie is still cleared below.

        except (JWTError, Exception):
            # Expired / invalid token — still safe to clear the cookie.
            pass

    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
    )
    return {"message": "Logged out successfully"}


# =========================================================
# FORGOT PASSWORD
# =========================================================

@router.post(
    "/forgot-password",
    response_model=PasswordResetResponse,
)
@limiter.limit("5/minute")
def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Initiate a password reset.

    Always returns the same generic message regardless of
    whether the email address is registered, to prevent
    account enumeration.

    A cryptographically random token is generated, its
    SHA-256 hash is stored, and the raw token is sent by
    email.  The token expires in 30 minutes.
    """

    GENERIC_RESPONSE = PasswordResetResponse(
        message=(
            "If an account exists for this email, "
            "a password reset link has been sent."
        )
    )

    normalized_email = _normalize_email(body.email)

    user = (
        db.query(UserDB)
        .filter(UserDB.email == normalized_email)
        .first()
    )

    # ---------------------------------------------------------
    # Generic response — do not reveal account existence.
    # ---------------------------------------------------------

    if not user or not user.is_active:
        return GENERIC_RESPONSE

    # ---------------------------------------------------------
    # Generate token and persist only its hash.
    # ---------------------------------------------------------

    raw_token = generate_password_reset_token()
    token_hash = hash_password_reset_token(raw_token)

    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(minutes=PASSWORD_RESET_EXPIRE_MINUTES)
    )

    reset_token = PasswordResetTokenDB(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
    )

    db.add(reset_token)

    try:
        db.commit()

    except Exception:
        db.rollback()
        # Still return generic response — do not leak errors.
        return GENERIC_RESPONSE

    # ---------------------------------------------------------
    # Send the reset email.
    # ---------------------------------------------------------

    try:
        send_password_reset_email(
            recipient_email=user.email,
            recipient_name=user.name,
            reset_token=raw_token,
        )

    except Exception:
        # Email delivery failed.  The token is already stored;
        # the user can request again.  Return generic response
        # so as not to reveal the failure mode externally.
        return GENERIC_RESPONSE

    return GENERIC_RESPONSE


# =========================================================
# RESET PASSWORD
# =========================================================

@router.post(
    "/reset-password",
    response_model=PasswordResetResponse,
)
@limiter.limit("5/minute")
def reset_password(
    body: ResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Complete a password reset.

    Validates the token, updates the password with bcrypt,
    marks the token as used, and commits atomically.

    Never returns the token or the new password in the
    response.
    """

    token_hash = hash_password_reset_token(body.token)

    reset_record = (
        db.query(PasswordResetTokenDB)
        .filter(PasswordResetTokenDB.token_hash == token_hash)
        .first()
    )

    now = datetime.now(timezone.utc)

    # ---------------------------------------------------------
    # Token not found
    # ---------------------------------------------------------

    if not reset_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset link.",
        )

    # ---------------------------------------------------------
    # Already used
    # ---------------------------------------------------------

    if reset_record.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This password reset link has already been used.",
        )

    # ---------------------------------------------------------
    # Expiration
    # ---------------------------------------------------------

    expires_at = reset_record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This password reset link has expired.",
        )

    # ---------------------------------------------------------
    # Constant-time token verification
    # ---------------------------------------------------------

    if not verify_password_reset_token(
        body.token,
        reset_record.token_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset link.",
        )

    # ---------------------------------------------------------
    # Load the owning user
    # ---------------------------------------------------------

    user = (
        db.query(UserDB)
        .filter(UserDB.id == reset_record.user_id)
        .first()
    )

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset link.",
        )

    # ---------------------------------------------------------
    # Update password, consume reset token, and set global
    # revocation fence — all three changes are atomic.
    #
    # tokens_valid_after is set to current whole-second UTC.
    # The JWT iat comparison uses strict < so tokens issued
    # in the same second as the fence are accepted (valid
    # post-reset logins).  Tokens issued strictly before the
    # fence second are always rejected.
    # ---------------------------------------------------------

    user.password_hash = hash_password(body.new_password)
    reset_record.used_at = now
    user.tokens_valid_after = now.replace(microsecond=0)

    try:
        db.commit()

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password reset failed. Please try again.",
        )

    return PasswordResetResponse(
        message="Your password has been reset successfully.",
    )


# =========================================================
# ACCEPT INVITATION
# =========================================================


class AcceptInviteRequest(BaseModel):
    email: EmailStr
    token: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=8, max_length=128)


@router.post("/accept-invite")
@limiter.limit("10/minute")
def accept_invite(
    body: AcceptInviteRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Accept a pharmacist invitation.

    Validates the invitation token, sets the invitee's password,
    marks email verified, and activates the account.

    This endpoint is the only path to activating an invited account.
    Regular login is blocked until this step completes.
    """

    normalized_email = _normalize_email(body.email)

    user = (
        db.query(UserDB)
        .filter(UserDB.email == normalized_email)
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid invitation",
        )

    # Must be an unverified, inactive pharmacist with a pending token.
    if user.email_verified or user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation has already been used",
        )

    if not user.email_verification_token_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid invitation",
        )

    expires_at = _as_utc_datetime(user.email_verification_expires_at)

    if not expires_at or expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Invitation has expired. "
                "Ask the inviting pharmacist to send a new invitation."
            ),
        )

    if not verify_email_verification_token(
        body.token,
        user.email_verification_token_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid invitation token",
        )

    # Set password, verify, and activate atomically.
    user.password_hash = hash_password(body.password)
    user.email_verified = True
    user.is_active = True
    user.email_verification_token_hash = None
    user.email_verification_expires_at = None
    user.email_verification_sent_at = None

    try:
        db.commit()
        db.refresh(user)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to accept invitation. Please try again.",
        )

    return {
        "message": (
            "Invitation accepted. Your account is now active. "
            "Please sign in."
        ),
        "email": user.email,
    }
