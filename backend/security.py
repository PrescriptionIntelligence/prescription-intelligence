from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext


# =========================================================
# SECURITY CONFIGURATION
# =========================================================

# IMPORTANT:
# For local development this fallback is acceptable.
# Before production deployment, set SECRET_KEY in .env.
SECRET_KEY = "prescription-intelligence-development-secret-key"

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