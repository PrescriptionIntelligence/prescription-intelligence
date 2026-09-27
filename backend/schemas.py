from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)
from typing import Any, Optional
from uuid import UUID
from datetime import date, datetime


# =========================================================
# MEDICINE
# =========================================================

class DoseComponent(BaseModel):
    value: float
    unit: str


class MedicineEvidence(BaseModel):
    accepted: Optional[bool] = None
    full_text_similarity: Optional[float] = None
    token_similarity: Optional[float] = None
    token_coverage: Optional[float] = None
    exact_match: Optional[bool] = None
    prefix_match: Optional[bool] = None
    ocr_corrected: Optional[bool] = None
    candidate_variant: Optional[str] = None
    second_best_score: Optional[float] = None
    ranked_results: list[dict] = Field(default_factory=list)


class MedicineBase(BaseModel):
    name: str
    generic_name: Optional[str] = None
    brand_name: Optional[str] = None

    strength_value: float | str | None = None
    strength_unit: Optional[str] = None
    strength_components: list[DoseComponent] = Field(
        default_factory=list
    )

    dose_value: Optional[float] = None
    dose_unit: Optional[str] = None

    daily_dose_value: Optional[float] = None
    daily_dose_unit: Optional[str] = None
    daily_dose_components: list[DoseComponent] = Field(
        default_factory=list
    )

    route: Optional[str] = None

    frequency_value: Optional[float] = None
    frequency_unit: Optional[str] = None

    duration_value: Optional[float] = None
    duration_unit: Optional[str] = None

    instructions: Optional[str] = None

    extraction_confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    normalization_confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    confidence: Optional[float] = None
    needs_review: Optional[bool] = None
    matched_term: Optional[str] = None
    evidence: Optional[MedicineEvidence] = None
    raw_text: Optional[str] = None
    status: Optional[str] = None

    @field_validator(
        "strength_components",
        "daily_dose_components",
        mode="before",
    )
    @classmethod
    def none_to_empty_list(cls, value):
        return [] if value is None else value


class MedicineCreate(MedicineBase):
    pass


class MedicineResponse(MedicineBase):
    id: UUID

    model_config = {
        "from_attributes": True
    }


# =========================================================
# PRESCRIPTION
# =========================================================

class PrescriptionCreate(BaseModel):
    prescription_id: str
    raw_text: Optional[str] = None
    medicines: list[MedicineCreate] = Field(
        default_factory=list
    )


class SafetyFlagResponse(BaseModel):
    type: str
    severity: str
    medicine: Optional[str] = None
    message: str


class AssignedCustomerResponse(BaseModel):
    """Minimal customer assignment metadata returned with a prescription."""

    id: UUID
    name: str
    customer_code: str


class PrescriptionResponse(BaseModel):
    id: UUID
    prescription_id: str
    raw_text: Optional[str] = None
    status: str
    review_status: str = "pending"
    safety_flags: list[Any] = Field(
        default_factory=list
    )

    file_name: Optional[str] = None
    file_type: Optional[str] = None
    # has_image indicates whether a prescription image is
    # available via GET /prescriptions/{id}/image.
    # The internal filesystem path is never returned.
    has_image: bool = False

    # Minimal assigned-customer metadata; None when no customer is assigned.
    assigned_customer: Optional[AssignedCustomerResponse] = None

    created_at: datetime
    updated_at: Optional[datetime] = None

    medicines: list[MedicineResponse] = Field(
        default_factory=list
    )

    model_config = {
        "from_attributes": True
    }

    @model_validator(mode="before")
    @classmethod
    def _derive_has_image(cls, data: Any) -> Any:
        """
        Derive has_image from file_path on the ORM object.
        file_path itself is not included in the schema so
        the filesystem path is never serialised to clients.

        Also derives assigned_customer from the customer relationship
        when present, exposing only the three fields needed by the
        pharmacist assignment UI.
        """
        if not isinstance(data, dict):
            # ORM instance — project to a plain dict so
            # Pydantic never sees file_path as a schema field
            customer = data.customer
            return {
                "id": data.id,
                "prescription_id": data.prescription_id,
                "raw_text": data.raw_text,
                "status": data.status,
                "review_status": data.review_status or "pending",
                "safety_flags": data.safety_flags or [],
                "file_name": data.file_name,
                "file_type": data.file_type,
                "has_image": bool(data.file_path),
                "assigned_customer": (
                    {
                        "id": customer.id,
                        "name": customer.name,
                        "customer_code": customer.customer_code,
                    }
                    if customer is not None
                    else None
                ),
                "created_at": data.created_at,
                "updated_at": data.updated_at,
                "medicines": list(data.medicines),
            }
        # dict input: has_image may already be set;
        # default False is applied by the field definition
        return data


class PrescriptionUploadResponse(BaseModel):
    message: str
    prescription_id: str
    file_name: str
    file_type: str
    # file_path and stored_filename are intentionally
    # omitted — internal filesystem paths must not be
    # returned to clients.
    status: str
    raw_text: Optional[str] = None

    medicines: list[MedicineBase] = Field(
        default_factory=list
    )

    safety_flags: list[Any] = Field(
        default_factory=list
    )

    analysis_metadata: Optional[dict] = None
    interpretation: Optional[dict] = None
    prescription_plan: Optional[dict] = None
    safety_analysis: Optional[dict] = None

    # evidence_chains is a parallel list aligned with
    # medicines — one evidence chain per medicine.
    # It is pharmacist-facing explainability context and
    # never exposes internal filesystem paths or secrets.
    evidence_chains: list[Any] = Field(
        default_factory=list
    )


# =========================================================
# DASHBOARD
# =========================================================

class RecentPrescriptionSummary(BaseModel):
    prescription_id: str
    file_name: Optional[str] = None
    created_at: str
    status: str
    medicine_count: int
    safety_count: int
    avg_confidence: Optional[float] = None


class DashboardStatsResponse(BaseModel):
    total_prescriptions: int
    total_medicines: int
    prescriptions_with_alerts: int
    needs_review: int
    recent_prescriptions: list[RecentPrescriptionSummary]


# =========================================================
# HUMAN REVIEW WORKFLOW
# =========================================================

class ReviewFinding(BaseModel):
    finding_type: str = Field(
        min_length=1,
        max_length=100,
    )

    finding_index: Optional[int] = Field(
        default=None,
        ge=0,
    )

    finding_data: dict[str, Any] = Field(
        default_factory=dict,
    )


class ReviewActionRequest(BaseModel):
    action: str = Field(
        min_length=1,
        max_length=30,
    )

    finding: Optional[ReviewFinding] = None

    note: Optional[str] = Field(
        default=None,
        max_length=5000,
    )


class ReviewStatusResponse(BaseModel):
    prescription_id: str
    review_status: str

    reviewed_by_id: Optional[UUID] = None
    reviewed_at: Optional[datetime] = None
    review_notes: Optional[str] = None

    reviewer: Optional[dict[str, Any]] = None

    high_priority_findings: int = 0
    total_findings: int = 0
    unresolved_findings: int = 0
    can_complete_review: bool = False


class ReviewAuditResponse(BaseModel):
    id: UUID

    prescription_id: UUID
    reviewer_id: UUID

    action: str

    previous_status: str
    new_status: str

    finding_type: Optional[str] = None
    finding_data: Optional[dict[str, Any]] = None

    note: Optional[str] = None

    created_at: datetime

    model_config = {
        "from_attributes": True
    }


class ReviewHistoryResponse(BaseModel):
    prescription_id: str
    current_status: str
    audits: list[ReviewAuditResponse] = Field(
        default_factory=list
    )


# =========================================================
# ACCOUNT / ROLE MANAGEMENT
# =========================================================

class PharmacyRegisterRequest(BaseModel):
    name: str = Field(
        min_length=2,
        max_length=200,
    )

    email: str

    password: str = Field(
        min_length=8,
        max_length=128,
    )

    pharmacy_name: str = Field(
        min_length=2,
        max_length=200,
    )


class CustomerRegisterRequest(BaseModel):
    name: str = Field(
        min_length=2,
        max_length=200,
    )

    email: str

    password: str = Field(
        min_length=8,
        max_length=128,
    )

    phone: Optional[str] = Field(
        default=None,
        max_length=30,
    )

    customer_code: Optional[str] = Field(
        default=None,
        max_length=50,
    )


class LoginRequest(BaseModel):
    email: str

    password: str = Field(
        min_length=1,
        max_length=128,
    )


class UserResponse(BaseModel):
    id: UUID
    name: str
    email: str
    role: str
    organization_id: Optional[UUID] = None
    is_active: bool

    model_config = {
        "from_attributes": True
    }


class OrganizationResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    is_active: bool = True

    model_config = {
        "from_attributes": True
    }


class AuthResponse(BaseModel):
    message: str
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
    organization: Optional[OrganizationResponse] = None


# =========================================================
# CUSTOMER
# =========================================================

class CustomerProfileResponse(BaseModel):
    id: UUID
    user_id: Optional[UUID] = None
    organization_id: UUID
    customer_code: str
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    date_of_birth: Optional[datetime] = None
    address: Optional[str] = None
    is_active: bool

    model_config = {
        "from_attributes": True
    }


class CustomerCreateRequest(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=200,
    )

    phone: Optional[str] = Field(
        default=None,
        max_length=30,
    )

    email: Optional[str] = Field(
        default=None,
        max_length=320,
    )

    date_of_birth: Optional[date] = None

    address: Optional[str] = Field(
        default=None,
        max_length=1000,
    )

    notes: Optional[str] = Field(
        default=None,
        max_length=5000,
    )


class CustomerResponse(BaseModel):
    id: UUID
    customer_code: str
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    date_of_birth: Optional[date] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool
    organization_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True
    }


class CustomerSearchResponse(BaseModel):
    id: UUID
    customer_code: str
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    is_active: bool
    organization_id: UUID

    model_config = {
        "from_attributes": True
    }


class PrescriptionCustomerAssignRequest(BaseModel):
    customer_id: UUID


# =========================================================
# EMAIL VERIFICATION
# =========================================================

class VerifyEmailRequest(BaseModel):
    email: EmailStr

    token: str = Field(
        min_length=20,
        max_length=200,
    )


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class EmailVerificationResponse(BaseModel):
    message: str
    email_verified: bool


# =========================================================
# PASSWORD RESET
# =========================================================

class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(
        min_length=20,
        max_length=200,
    )

    new_password: str = Field(
        min_length=8,
        max_length=128,
    )


class PasswordResetResponse(BaseModel):
    message: str


class PharmacyLinkRequestResponse(BaseModel):
    """Returned to the pharmacist after creating a pending link request."""

    message: str
    request_id: UUID
    customer_id: UUID
    organization_id: UUID
    # The raw token is returned once so the pharmacist/system
    # can deliver it to the customer (e.g. via SMS/email).
    token: str
    expires_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PharmacyLinkAcceptRequest(BaseModel):
    """Submitted by the authenticated customer to accept the link."""

    token: str = Field(min_length=1, max_length=256)
