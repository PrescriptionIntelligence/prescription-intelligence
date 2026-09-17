from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    JSON,
    String,
    Text,
    Boolean,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


# =========================================================
# ORGANIZATION / PHARMACY
# =========================================================

class OrganizationDB(Base):
    __tablename__ = "organizations"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    slug: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
    )

    phone: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    address: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    users: Mapped[list["UserDB"]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )

    customers: Mapped[list["CustomerDB"]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )

    prescriptions: Mapped[list["PrescriptionDB"]] = relationship(
        back_populates="organization",
    )

    customer_memberships: Mapped[
        list["CustomerOrganizationDB"]
    ] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )


# =========================================================
# USER / ACCOUNT
# =========================================================

class UserDB(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )

    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id"),
        nullable=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )

    # -----------------------------------------------------
    # Email verification
    # -----------------------------------------------------

    email_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )

    email_verification_token_hash: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    email_verification_expires_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    email_verification_sent_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    password_hash: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    # pharmacist | admin | customer
    role: Mapped[str] = mapped_column(
        String(30),
        default="pharmacist",
        nullable=False,
        index=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    organization: Mapped["OrganizationDB | None"] = relationship(
        back_populates="users",
    )

    uploaded_prescriptions: Mapped[
        list["PrescriptionDB"]
    ] = relationship(
        back_populates="uploaded_by",
        foreign_keys="PrescriptionDB.uploaded_by_id",
    )

    reviewed_prescriptions: Mapped[
        list["PrescriptionDB"]
    ] = relationship(
        back_populates="reviewed_by",
        foreign_keys="PrescriptionDB.reviewed_by_id",
    )

    customer_profile: Mapped[
        "CustomerDB | None"
    ] = relationship(
        back_populates="user",
        foreign_keys="CustomerDB.user_id",
        uselist=False,
    )


# =========================================================
# CUSTOMER / PATIENT
# =========================================================

class CustomerDB(Base):
    __tablename__ = "customers"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )

    # Optional link to a customer login account.
    #
    # A pharmacy can create a customer profile before the
    # customer creates an account, so this remains nullable.
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        unique=True,
        index=True,
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )

    customer_code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    phone: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        index=True,
    )

    email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    date_of_birth: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    address: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user: Mapped["UserDB | None"] = relationship(
        back_populates="customer_profile",
        foreign_keys=[user_id],
        uselist=False,
    )

    organization: Mapped["OrganizationDB"] = relationship(
        back_populates="customers",
    )

    prescriptions: Mapped[
        list["PrescriptionDB"]
    ] = relationship(
        back_populates="customer",
    )

    organization_memberships: Mapped[
        list["CustomerOrganizationDB"]
    ] = relationship(
        back_populates="customer",
        foreign_keys="CustomerOrganizationDB.customer_id",
        cascade="all, delete-orphan",
    )


class CustomerOrganizationDB(Base):
    """
    Associates a customer with one or more pharmacy organizations.

    A customer can use multiple pharmacies while keeping
    one global customer account.
    """

    __tablename__ = "customer_organizations"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )

    customer_id: Mapped[UUID] = mapped_column(
        ForeignKey("customers.id"),
        nullable=False,
        index=True,
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    customer: Mapped["CustomerDB"] = relationship(
        back_populates="organization_memberships",
        foreign_keys=[customer_id],
    )

    organization: Mapped["OrganizationDB"] = relationship(
        back_populates="customer_memberships",
        foreign_keys=[organization_id],
    )

    __table_args__ = (
        UniqueConstraint(
            "customer_id",
            "organization_id",
            name="uq_customer_organization",
        ),
    )


# =========================================================
# PRESCRIPTION
# =========================================================

class PrescriptionDB(Base):
    __tablename__ = "prescriptions"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )

    prescription_id: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
    )

    # -----------------------------------------------------
    # Ownership
    # -----------------------------------------------------

    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id"),
        nullable=True,
        index=True,
    )

    uploaded_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    customer_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("customers.id"),
        nullable=True,
        index=True,
    )

    # -----------------------------------------------------
    # Prescription content
    # -----------------------------------------------------

    raw_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="uploaded",
        index=True,
    )

    # -----------------------------------------------------
    # Human review
    # -----------------------------------------------------

    review_status: Mapped[str] = mapped_column(
        String(30),
        default="pending",
        index=True,
    )

    reviewed_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    review_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # -----------------------------------------------------
    # Safety intelligence
    # -----------------------------------------------------

    safety_flags: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )

    # -----------------------------------------------------
    # Uploaded file
    # -----------------------------------------------------

    file_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    file_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    file_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # -----------------------------------------------------
    # Timestamps
    # -----------------------------------------------------

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # -----------------------------------------------------
    # Relationships
    # -----------------------------------------------------

    organization: Mapped[
        "OrganizationDB | None"
    ] = relationship(
        back_populates="prescriptions",
    )

    uploaded_by: Mapped[
        "UserDB | None"
    ] = relationship(
        back_populates="uploaded_prescriptions",
        foreign_keys=[uploaded_by_id],
    )

    reviewed_by: Mapped[
        "UserDB | None"
    ] = relationship(
        back_populates="reviewed_prescriptions",
        foreign_keys=[reviewed_by_id],
    )

    customer: Mapped[
        "CustomerDB | None"
    ] = relationship(
        back_populates="prescriptions",
    )

    medicines: Mapped[
        list["MedicineDB"]
    ] = relationship(
        back_populates="prescription",
        cascade="all, delete-orphan",
    )


# =========================================================
# PRESCRIPTION REVIEW AUDIT
# =========================================================

class ReviewAuditDB(Base):
    """
    Immutable audit record for every human review action.

    This table records what happened during prescription review.
    Existing records should never be edited or deleted as part
    of normal application behavior.
    """

    __tablename__ = "review_audits"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )

    prescription_id: Mapped[UUID] = mapped_column(
        ForeignKey("prescriptions.id"),
        nullable=False,
        index=True,
    )

    reviewer_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    # confirm | correct | dismiss | clarify | start_review
    action: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    previous_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    new_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    # Example:
    # strength_conflict
    # ambiguous_medicine
    # interaction
    # ocr_empty
    finding_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    # Snapshot of the finding at the moment of review.
    finding_data: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    prescription: Mapped["PrescriptionDB"] = relationship(
        foreign_keys=[prescription_id],
    )

    reviewer: Mapped["UserDB"] = relationship(
        foreign_keys=[reviewer_id],
    )


# =========================================================
# MEDICINE
# =========================================================

class MedicineDB(Base):
    __tablename__ = "medicines"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )

    prescription_id: Mapped[UUID] = mapped_column(
        ForeignKey("prescriptions.id"),
        index=True,
    )

    # -----------------------------------------------------
    # Identification
    # -----------------------------------------------------

    name: Mapped[str] = mapped_column(
        String(200),
    )

    generic_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    brand_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    # -----------------------------------------------------
    # Strength
    # -----------------------------------------------------

    strength_value: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    strength_unit: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    strength_components: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )

    # -----------------------------------------------------
    # Dose
    # -----------------------------------------------------

    dose_value: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    dose_unit: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    # -----------------------------------------------------
    # Calculated daily dose
    # -----------------------------------------------------

    daily_dose_value: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    daily_dose_unit: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    daily_dose_components: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )

    # -----------------------------------------------------
    # Administration
    # -----------------------------------------------------

    route: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    # -----------------------------------------------------
    # Frequency
    # -----------------------------------------------------

    frequency_value: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    frequency_unit: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    # -----------------------------------------------------
    # Duration
    # -----------------------------------------------------

    duration_value: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    duration_unit: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    # -----------------------------------------------------
    # Instructions
    # -----------------------------------------------------

    instructions: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # -----------------------------------------------------
    # AI confidence
    # -----------------------------------------------------

    extraction_confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    normalization_confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    # -----------------------------------------------------
    # Relationship
    # -----------------------------------------------------

    prescription: Mapped["PrescriptionDB"] = relationship(
        back_populates="medicines",
    )


# =========================================================
# ORGANIZATION USAGE PLAN
#
# This model supports future monetization without implementing
# billing. It defines per-organization usage limits and the
# current plan tier.
#
# Tiers:
#   free         — limited prescription analysis per month
#   professional — larger volume, full pharmacist workflow
#   enterprise   — organization-wide, higher limits, analytics
#
# Enforcement:
#   - check_prescription_limit() raises 429 when the
#     monthly prescription limit is reached.
#   - Limits are enforced server-side only.
#   - No billing integration is implemented yet.
#   - Limits can be overridden per-organization by admin.
# =========================================================

class OrganizationPlanDB(Base):
    __tablename__ = "organization_plans"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "organizations.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        unique=True,
    )

    # Plan tier: free | professional | enterprise
    plan_tier: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="free",
    )

    # Monthly prescription analysis limit.
    # None = unlimited.
    monthly_prescription_limit: Mapped[int | None] = mapped_column(
        nullable=True,
        default=25,
    )

    # When the current billing period started.
    # Used to calculate monthly usage.
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Total prescriptions analyzed in the current period.
    period_prescription_count: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
    )

    # Whether pharmacist review workflow is enabled.
    review_workflow_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    # Whether PDF report generation is enabled.
    # Default is False — free-tier plans do not include PDF reports.
    # Professional and enterprise plans enable this via plan management.
    pdf_reports_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    # Optional override note (for admin use).
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationship back to organization
    organization: Mapped["OrganizationDB"] = relationship(
        foreign_keys=[organization_id],
    )
