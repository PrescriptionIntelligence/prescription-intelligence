import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext


# =========================================================
# SECURITY CONFIGURATION
# =========================================================

# SECRET_KEY MUST be set in .env for production.
# A development fallback is provided so the server starts
# locally without configuration, but this value must be
# replaced before any public deployment.
_env_secret = os.getenv("SECRET_KEY")
SECRET_KEY = (
    _env_secret
    if _env_secret
    else "prescription-intelligence-development-secret-key-change-in-production"
)

ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24


# =========================================================
# PASSWORD HASHING
# =========================================================

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)


def hash_password(password: str) -> str:
    """
    Convert a plain-text password into a secure bcrypt hash.
    """
    return pwd_context.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    """
    Verify a plain-text password against its bcrypt hash.
    """
    return pwd_context.verify(
        plain_password,
        hashed_password,
    )


# =========================================================
# JWT
# =========================================================

def create_access_token(
    user_id: str,
    role: str,
    organization_id: Optional[str] = None,
) -> str:
    """
    Create an access token containing the minimum identity
    information required by the API.
    """

    expire = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload = {
        "sub": user_id,
        "role": role,
        "organization_id": organization_id,
        "exp": expire,
    }

    return jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def decode_access_token(token: str) -> dict:
    """
    Decode and validate a JWT.

    Raises JWTError if the token is invalid or expired.
    """

    return jwt.decode(
        token,
        SECRET_KEY,
        algorithms=[ALGORITHM],
    )