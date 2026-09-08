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

    password_hash: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    # pharmacist | admin
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

    uploaded_prescriptions: Mapped[list["PrescriptionDB"]] = relationship(
        back_populates="uploaded_by",
        foreign_keys="PrescriptionDB.uploaded_by_id",
    )

    reviewed_prescriptions: Mapped[list["PrescriptionDB"]] = relationship(
        back_populates="reviewed_by",
        foreign_keys="PrescriptionDB.reviewed_by_id",
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

    organization: Mapped["OrganizationDB"] = relationship(
        back_populates="customers",
    )

    prescriptions: Mapped[list["PrescriptionDB"]] = relationship(
        back_populates="customer",
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

    organization: Mapped["OrganizationDB | None"] = relationship(
        back_populates="prescriptions",
    )

    uploaded_by: Mapped["UserDB | None"] = relationship(
        back_populates="uploaded_prescriptions",
        foreign_keys=[uploaded_by_id],
    )

    reviewed_by: Mapped["UserDB | None"] = relationship(
        back_populates="reviewed_prescriptions",
        foreign_keys=[reviewed_by_id],
    )

    customer: Mapped["CustomerDB | None"] = relationship(
        back_populates="prescriptions",
    )

    medicines: Mapped[list["MedicineDB"]] = relationship(
        back_populates="prescription",
        cascade="all, delete-orphan",
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