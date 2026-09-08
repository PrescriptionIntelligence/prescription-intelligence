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
    # Identification
    name: str
    generic_name: Optional[str] = None
    brand_name: Optional[str] = None

    # Strength
    strength_value: float | str | None = None
    strength_unit: Optional[str] = None
    strength_components: list[DoseComponent] = Field(default_factory=list)

    # Dose
    dose_value: Optional[float] = None
    dose_unit: Optional[str] = None

    # Calculated daily dose
    daily_dose_value: Optional[float] = None
    daily_dose_unit: Optional[str] = None
    daily_dose_components: list[DoseComponent] = Field(default_factory=list)

    # Administration
    route: Optional[str] = None

    # Frequency
    frequency_value: Optional[float] = None
    frequency_unit: Optional[str] = None

    # Duration
    duration_value: Optional[float] = None
    duration_unit: Optional[str] = None

    # Original prescription instruction
    instructions: Optional[str] = None

    # AI confidence
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

    # Intelligence / evidence
    confidence: Optional[float] = None
    needs_review: Optional[bool] = None
    matched_term: Optional[str] = None
    evidence: Optional[MedicineEvidence] = None
    raw_text: Optional[str] = None
    status: Optional[str] = None

    # Convert database NULL -> empty list
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
    medicines: list[MedicineBase] = Field(default_factory=list)
    safety_flags: list[Any] = Field(default_factory=list)
    analysis_metadata: Optional[dict] = None


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
