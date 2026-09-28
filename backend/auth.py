from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import RevokedAccessTokenDB, UserDB
from backend.security import COOKIE_NAME, decode_access_token


# =========================================================
# AUTHENTICATION
# =========================================================

# auto_error=False so we can implement the cookie/Bearer
# fallback ourselves without FastAPI raising 401 prematurely.
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/token",
    auto_error=False,
)


def get_current_user(
    bearer_token: Optional[str] = Depends(oauth2_scheme),
    cookie_token: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
    db: Session = Depends(get_db),
) -> UserDB:
    """
    Resolve the authenticated user from a JWT.

    Token extraction priority:
        1. HttpOnly cookie  (pi_access_token)
        2. Authorization: Bearer <token>
        3. 401 if neither is present / valid

    Validation order:
        1. Signature + expiry    (python-jose)
        2. token_type == "access"
        3. sub present and valid UUID
        4. jti present and non-empty
        5. user exists in DB
        6. user.is_active
        7. tokens_valid_after fence (global: password-reset invalidation)
        8. jti denylist           (per-token: logout invalidation)
    """

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={
            "WWW-Authenticate": "Bearer",
        },
    )

    # Prefer the cookie; fall back to the Authorization header.
    # An invalid/revoked cookie is NOT bypassed by a valid Bearer —
    # the cookie takes precedence and authentication fails.
    token = cookie_token or bearer_token

    if not token:
        raise credentials_exception

    try:
        payload = decode_access_token(token)

        if payload.get("token_type") != "access":
            raise credentials_exception

        user_id = payload.get("sub")
        if not user_id:
            raise credentials_exception

        jti = payload.get("jti")
        if not jti:
            # Tokens without jti pre-date P7.12-D — reject them.
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    try:
        user_uuid = UUID(user_id)
    except (ValueError, AttributeError):
        raise credentials_exception

    user = (
        db.query(UserDB)
        .filter(UserDB.id == user_uuid)
        .first()
    )

    if not user:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    # -----------------------------------------------------------------
    # Global fence: password-reset invalidation.
    #
    # JWT iat is encoded by python-jose as a Unix integer (seconds).
    # tokens_valid_after is stored at whole-second precision
    # (now.replace(microsecond=0)).
    #
    # Comparison: iat_dt <= tva  (i.e. reject tokens issued AT OR
    # BEFORE the fence second).
    #
    # A token issued in the SAME second as the fence is considered
    # pre-reset and is rejected.  A new post-reset login produces a
    # token with iat at the next second (or later), which passes.
    #
    # SQLite stores TIMESTAMPTZ as naive UTC; normalise before compare.
    # -----------------------------------------------------------------
    if user.tokens_valid_after is not None:
        issued_at = payload.get("iat")
        if issued_at is None:
            raise credentials_exception

        try:
            issued_at_dt = datetime.fromtimestamp(
                int(issued_at),
                tz=timezone.utc,
            )
        except (TypeError, ValueError, OverflowError):
            raise credentials_exception

        tva = user.tokens_valid_after
        if tva.tzinfo is None:
            tva = tva.replace(tzinfo=timezone.utc)

        if issued_at_dt <= tva:
            raise credentials_exception

    # -----------------------------------------------------------------
    # Per-token denylist: logout invalidation.
    #
    # If this jti appears in revoked_access_tokens the token was
    # explicitly revoked (logout).  The row is kept until the
    # token's own exp passes, after which the token would be
    # rejected by python-jose anyway.
    # -----------------------------------------------------------------
    revoked = (
        db.query(RevokedAccessTokenDB)
        .filter(RevokedAccessTokenDB.jti == jti)
        .first()
    )
    if revoked is not None:
        raise credentials_exception

    return user


# =========================================================
# ROLE HELPERS
# =========================================================

def require_pharmacist(
    current_user: UserDB = Depends(get_current_user),
) -> UserDB:
    if current_user.role not in {"pharmacist", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Pharmacist access required",
        )

    return current_user


def require_customer(
    current_user: UserDB = Depends(get_current_user),
) -> UserDB:
    if current_user.role != "customer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customer access required",
        )

    return current_user


def require_admin(
    current_user: UserDB = Depends(get_current_user),
) -> UserDB:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required",
        )

    return current_user


def require_pharmacy_staff(
    current_user: UserDB = Depends(get_current_user),
) -> UserDB:
    """
    Access for pharmacy-side users only.

    Admin is intentionally excluded here because platform-wide
    admin operations should use require_admin explicitly.
    """
    if current_user.role != "pharmacist":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Pharmacy staff access required",
        )

    return current_user


def require_any_authenticated_user(
    current_user: UserDB = Depends(get_current_user),
) -> UserDB:
    return current_user
