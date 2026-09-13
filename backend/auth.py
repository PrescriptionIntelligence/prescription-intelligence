from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import UserDB
from backend.security import decode_access_token


# =========================================================
# AUTHENTICATION
# =========================================================

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/token",
)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> UserDB:
    """
    Resolve the authenticated user from the JWT.
    """

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={
            "WWW-Authenticate": "Bearer",
        },
    )

    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")

        if not user_id:
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
