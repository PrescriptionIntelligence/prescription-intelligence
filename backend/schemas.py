from pydantic import BaseModel, Field, field_validator
from typing import Any, Optional
from uuid import UUID
from datetime import datetime


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
    strength_components: list[DoseComponent] = Field(default_factory=list)

    dose_value: Optional[float] = None
    dose_unit: Optional[str] = None

    daily_dose_value: Optional[float] = None
    daily_dose_unit: Optional[str] = None
    daily_dose_components: list[DoseComponent] = Field(default_factory=list)

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


class PrescriptionCreate(BaseModel):
    prescription_id: str
    raw_text: Optional[str] = None
    medicines: list[MedicineCreate] = Field(default_factory=list)


class SafetyFlagResponse(BaseModel):
    type: str
    severity: str
    medicine: Optional[str] = None
    message: str


class PrescriptionResponse(BaseModel):
    id: UUID
    prescription_id: str
    raw_text: Optional[str] = None
    status: str
    safety_flags: list[Any] = Field(default_factory=list)

    file_name: Optional[str] = None
    file_path: Optional[str] = None
    file_type: Optional[str] = None

    created_at: datetime
    updated_at: Optional[datetime] = None
    medicines: list[MedicineResponse] = Field(default_factory=list)

    model_config = {
        "from_attributes": True
    }


class PrescriptionUploadResponse(BaseModel):
    message: str
    prescription_id: str
    file_name: str
    file_type: str
    file_path: str
    stored_filename: Optional[str] = None
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


# ---------------------------------------------------------
# Dashboard
# ---------------------------------------------------------

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


# ---------------------------------------------------------
# Human Review Workflow
# ---------------------------------------------------------

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
        default_factory=list,
    )


# ---------------------------------------------------------
# Account / Role Management
# ---------------------------------------------------------

class PharmacyRegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    email: str
    password: str = Field(min_length=8, max_length=128)
    pharmacy_name: str = Field(min_length=2, max_length=200)


class CustomerRegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    email: str
    password: str = Field(min_length=8, max_length=128)
    phone: Optional[str] = Field(default=None, max_length=30)
    customer_code: Optional[str] = Field(default=None, max_length=50)


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=128)


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

    model_config = {
        "from_attributes": True
    }


class AuthResponse(BaseModel):
    message: str
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
    organization: Optional[OrganizationResponse] = None


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
