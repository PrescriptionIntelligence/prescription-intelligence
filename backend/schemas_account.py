from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


# =========================================================
# AUTH
# =========================================================

class RegisterRequest(BaseModel):
    organization_name: str = Field(
        min_length=2,
        max_length=200,
    )

    name: str = Field(
        min_length=2,
        max_length=200,
    )

    email: EmailStr

    password: str = Field(
        min_length=8,
        max_length=128,
    )


class LoginRequest(BaseModel):
    email: EmailStr

    password: str = Field(
        min_length=1,
        max_length=128,
    )


class UserResponse(BaseModel):
    id: UUID
    name: str
    email: str
    role: str
    organization_id: UUID
    is_active: bool
    created_at: datetime

    model_config = {
        "from_attributes": True,
    }


class LoginResponse(BaseModel):
    token: str
    user: UserResponse


# =========================================================
# ORGANIZATION
# =========================================================

class OrganizationResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    is_active: bool
    created_at: datetime

    model_config = {
        "from_attributes": True,
    }


# =========================================================
# CUSTOMER
# =========================================================

class CustomerCreate(BaseModel):
    full_name: str = Field(
        min_length=2,
        max_length=200,
    )

    phone: str | None = Field(
        default=None,
        max_length=30,
    )

    email: EmailStr | None = None

    date_of_birth: str | None = Field(
        default=None,
        max_length=20,
    )

    address: str | None = None

    notes: str | None = None


class CustomerUpdate(BaseModel):
    full_name: str | None = Field(
        default=None,
        min_length=2,
        max_length=200,
    )

    phone: str | None = Field(
        default=None,
        max_length=30,
    )

    email: EmailStr | None = None

    date_of_birth: str | None = Field(
        default=None,
        max_length=20,
    )

    address: str | None = None

    notes: str | None = None

    is_active: bool | None = None


class CustomerResponse(BaseModel):
    id: UUID
    organization_id: UUID
    customer_code: str
    full_name: str
    phone: str | None
    email: str | None
    date_of_birth: str | None
    address: str | None
    notes: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
    }


# =========================================================
# REVIEW
# =========================================================

class ReviewCreate(BaseModel):
    status: str = Field(
        default="reviewed",
        max_length=30,
    )

    notes: str | None = None

    medicine_reviews: dict | None = None


class ReviewResponse(BaseModel):
    id: UUID
    prescription_id: UUID
    reviewer_user_id: UUID
    status: str
    notes: str | None
    medicine_reviews: dict | None
    reviewed_at: datetime

    model_config = {
        "from_attributes": True,
    }


# =========================================================
# SAFETY
# =========================================================

class SafetyFlagResponse(BaseModel):
    id: UUID
    prescription_id: UUID
    type: str
    severity: str
    medicine: str | None
    message: str
    resolved: bool
    created_at: datetime

    model_config = {
        "from_attributes": True,
    }