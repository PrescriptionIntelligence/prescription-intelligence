import logging
import os
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image

from backend.routers import (
    admin,
    auth,
    users,
    reviews,
    customers,
)

from fastapi import (
    Depends,
    FastAPI,
    File,
    HTTPException,
    Request,
    UploadFile,
)

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from backend.auth import (
    require_admin,
    require_any_authenticated_user,
    require_pharmacy_staff,
)

from backend.database import get_db

from backend.models import (
    CustomerDB,
    MedicineDB,
    PrescriptionDB,
    ReviewAuditDB,
    UserDB,
)

from backend.schemas import (
    DashboardStatsResponse,
    PrescriptionCreate,
    PrescriptionResponse,
    PrescriptionUploadResponse,
    PrescriptionCustomerAssignRequest,
)

from backend.services.customer_service import (
    customer_belongs_to_organization,
)

from backend.services.ocr_service import extract_text_from_image
from backend.services.prescription_pipeline import process_prescription
from backend.services.prescription_report import build_prescription_report
from backend.services.pdf_report_generator import generate_prescription_pdf
from backend.services.usage_plan import (
    check_prescription_limit,
    increment_prescription_usage,
    get_plan_status,
)


logger = logging.getLogger(__name__)


# =========================================================
# PATHS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent

UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


# =========================================================
# FASTAPI APPLICATION
# =========================================================

from backend.rate_limit import limiter

app = FastAPI(
    title="Prescription Intelligence API",
    description=(
        "AI-powered prescription intelligence "
        "and medication safety platform"
    ),
    version="1.0.0",
)

# Attach the limiter to the app so slowapi can locate it.
app.state.limiter = limiter

# Return HTTP 429 with a plain JSON body (never leaks account info).
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# =========================================================
# ROUTERS
# =========================================================

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(reviews.router)
app.include_router(customers.router)
app.include_router(admin.router)


# =========================================================
# CORS
# =========================================================

_allowed_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)


# =========================================================
# SECURITY HEADERS
# =========================================================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add minimal security headers to every response.

    Always added:
        X-Content-Type-Options: nosniff
        X-Frame-Options: DENY
        Referrer-Policy: strict-origin-when-cross-origin

    Only added when the request arrived over HTTPS
    (X-Forwarded-Proto: https from a reverse proxy, or a
    direct TLS connection):
        Strict-Transport-Security: max-age=31536000; includeSubDomains

    HSTS is intentionally withheld for plain HTTP so local
    development continues to work without requiring TLS.
    """

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Only set HSTS when the connection is over HTTPS.
        forwarded_proto = request.headers.get("x-forwarded-proto", "")
        if (
            forwarded_proto.lower() == "https"
            or request.url.scheme == "https"
        ):
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response


app.add_middleware(SecurityHeadersMiddleware)


# =========================================================
# ROOT
# =========================================================


@app.get("/")
def root():
    return {
        "project": "Prescription Intelligence",
        "status": "running",
        "version": "1.0.0",
    }


# =========================================================
# HEALTH
# =========================================================


@app.get("/health")
def health(db: Session = Depends(get_db)):
    """
    Health check endpoint.

    Verifies the application is running and the database
    connection is active. Returns 503 if the database is
    unreachable so load-balancers and orchestrators (k8s,
    ECS health checks) can detect the degraded state.
    """
    from fastapi.responses import JSONResponse
    from sqlalchemy import text

    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        db_status = "unavailable"

    is_healthy = db_status == "connected"
    payload = {
        "status": "healthy" if is_healthy else "degraded",
        "database": db_status,
        "version": "1.0.0",
    }
    return JSONResponse(content=payload, status_code=200 if is_healthy else 503)


# =========================================================
# ORGANIZATION PLAN / USAGE STATUS
# =========================================================


@app.get(
    "/usage",
    tags=["Usage"],
)
def get_usage_status(
    current_user: UserDB = Depends(
        require_pharmacy_staff
    ),
    db: Session = Depends(get_db),
):
    """
    Return the current organization's plan and usage status.

    Only pharmacy staff can access this endpoint.
    """

    if not current_user.organization_id:
        raise HTTPException(
            status_code=403,
            detail="Pharmacist is not associated with an organization",
        )

    return get_plan_status(
        organization_id=current_user.organization_id,
        db=db,
    )


# =========================================================
# DASHBOARD STATISTICS
# =========================================================


@app.get(
    "/dashboard/stats",
    response_model=DashboardStatsResponse,
    tags=["Dashboard"],
)
def get_dashboard_stats(
    current_user: UserDB = Depends(
        require_any_authenticated_user
    ),
    db: Session = Depends(get_db),
):
    """
    Return dashboard statistics according to the user's role.

    Pharmacist:
        Only their organization's data.

    Customer:
        Only their own prescriptions.

    Admin:
        Platform-wide statistics.
    """

    # -----------------------------------------------------
    # Determine prescription scope
    # -----------------------------------------------------

    prescription_query = db.query(
        PrescriptionDB
    )

    if current_user.role == "pharmacist":
        if not current_user.organization_id:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Pharmacist is not associated "
                    "with an organization"
                ),
            )

        prescription_query = prescription_query.filter(
            PrescriptionDB.organization_id
            == current_user.organization_id
        )

    elif current_user.role == "customer":
        customer = (
            db.query(CustomerDB)
            .filter(
                CustomerDB.user_id
                == current_user.id
            )
            .first()
        )

        if not customer:
            prescription_query = prescription_query.filter(
                PrescriptionDB.id == None
            )
        else:
            prescription_query = prescription_query.filter(
                PrescriptionDB.customer_id
                == customer.id
            )

    elif current_user.role == "admin":
        pass

    else:
        raise HTTPException(
            status_code=403,
            detail="Unsupported user role",
        )

    # -----------------------------------------------------
    # Total prescriptions
    # -----------------------------------------------------

    total_prescriptions = (
        prescription_query.with_entities(
            func.count(PrescriptionDB.id)
        ).scalar()
    ) or 0

    # -----------------------------------------------------
    # Total medicines
    # -----------------------------------------------------

    medicine_query = db.query(
        MedicineDB
    ).join(
        PrescriptionDB,
        MedicineDB.prescription_id
        == PrescriptionDB.id,
    )

    if current_user.role == "pharmacist":
        medicine_query = medicine_query.filter(
            PrescriptionDB.organization_id
            == current_user.organization_id
        )

    elif current_user.role == "customer":
        customer = (
            db.query(CustomerDB)
            .filter(
                CustomerDB.user_id
                == current_user.id
            )
            .first()
        )

        if customer:
            medicine_query = medicine_query.filter(
                PrescriptionDB.customer_id
                == customer.id
            )
        else:
            medicine_query = medicine_query.filter(
                PrescriptionDB.id == None
            )

    total_medicines = (
        medicine_query.with_entities(
            func.count(MedicineDB.id)
        ).scalar()
    ) or 0

    # -----------------------------------------------------
    # Prescriptions with safety flags
    # -----------------------------------------------------

    try:
        prescriptions_with_flags = (
            prescription_query.filter(
                PrescriptionDB.safety_flags.isnot(
                    None
                ),
                func.json_array_length(
                    PrescriptionDB.safety_flags
                ) > 0,
            ).with_entities(
                func.count(PrescriptionDB.id)
            ).scalar()
        ) or 0

    except Exception:
        db.rollback()
        prescriptions_with_flags = 0

    # -----------------------------------------------------
    # Prescriptions requiring review
    # -----------------------------------------------------
    # Count prescriptions whose review_status is "pending"
    # (or NULL for legacy rows).  This matches the link
    # destination /history?review_status=pending exactly.

    from sqlalchemy import or_ as _or

    review_query = (
        db.query(
            PrescriptionDB.id
        )
    )

    if current_user.role == "pharmacist":
        review_query = review_query.filter(
            PrescriptionDB.organization_id
            == current_user.organization_id
        )

    elif current_user.role == "customer":
        customer = (
            db.query(CustomerDB)
            .filter(
                CustomerDB.user_id
                == current_user.id
            )
            .first()
        )

        if customer:
            review_query = review_query.filter(
                PrescriptionDB.customer_id
                == customer.id
            )
        else:
            review_query = review_query.filter(
                PrescriptionDB.id == None
            )

    needs_review = (
        review_query.filter(
            _or(
                PrescriptionDB.review_status
                == "pending",
                PrescriptionDB.review_status.is_(
                    None
                ),
            )
        )
        .count()
    ) or 0

    # -----------------------------------------------------
    # Recent prescriptions
    # -----------------------------------------------------

    recent = (
        prescription_query
        .options(
            selectinload(
                PrescriptionDB.medicines
            )
        )
        .order_by(
            PrescriptionDB.created_at.desc()
        )
        .limit(5)
        .all()
    )

    recent_list = []

    for rx in recent:
        medicine_count = len(
            rx.medicines
        )

        safety_count = len(
            rx.safety_flags or []
        )

        medicine_confidences = []

        for medicine in rx.medicines:
            extraction = (
                medicine.extraction_confidence
            )
            normalization = (
                medicine.normalization_confidence
            )

            values = [
                v for v in (
                    extraction, normalization
                )
                if v is not None
            ]

            if values:
                medicine_confidences.append(
                    sum(values) / len(values)
                )

        avg_confidence = (
            round(
                sum(medicine_confidences)
                / len(medicine_confidences),
                2,
            )
            if medicine_confidences
            else None
        )

        recent_list.append(
            {
                "prescription_id": (
                    rx.prescription_id
                ),
                "file_name": rx.file_name,
                "created_at": (
                    rx.created_at.isoformat()
                ),
                "status": rx.status,
                "medicine_count": medicine_count,
                "safety_count": safety_count,
                "avg_confidence": avg_confidence,
            }
        )

    return {
        "total_prescriptions": total_prescriptions,
        "total_medicines": total_medicines,
        "prescriptions_with_alerts": (
            prescriptions_with_flags
        ),
        "needs_review": needs_review,
        "recent_prescriptions": recent_list,
    }


# =========================================================
# CREATE PRESCRIPTION MANUALLY
# =========================================================


@app.post(
    "/prescriptions",
    response_model=PrescriptionResponse,
    status_code=201,
    tags=["Prescriptions"],
)
def create_prescription(
    prescription: PrescriptionCreate,
    current_user: UserDB = Depends(
        require_pharmacy_staff
    ),
    db: Session = Depends(get_db),
):
    """
    Create a prescription manually.

    Only pharmacy staff can create prescriptions.

    The prescription is automatically assigned to:
        organization_id = pharmacist's pharmacy
        uploaded_by_id = current pharmacist
    """

    if not current_user.organization_id:
        raise HTTPException(
            status_code=403,
            detail=(
                "Pharmacist is not associated "
                "with an organization"
            ),
        )

    # ---------------------------------------------------------
    # Server-side quota check — must run before any DB writes.
    # Mirrors the same enforcement used in /prescriptions/upload.
    # ---------------------------------------------------------
    check_prescription_limit(
        organization_id=current_user.organization_id,
        db=db,
    )

    existing = (
        db.query(PrescriptionDB)
        .filter(
            PrescriptionDB.prescription_id
            == prescription.prescription_id
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Prescription ID already exists",
        )

    db_prescription = PrescriptionDB(
        prescription_id=(
            prescription.prescription_id
        ),
        raw_text=prescription.raw_text,
        status="uploaded",
        organization_id=(
            current_user.organization_id
        ),
        uploaded_by_id=current_user.id,
    )

    for medicine in prescription.medicines:
        strength_value = medicine.strength_value

        if strength_value is not None:
            strength_value = str(
                strength_value
            )

        db_medicine = MedicineDB(
            name=medicine.name,
            generic_name=medicine.generic_name,
            brand_name=medicine.brand_name,
            strength_value=strength_value,
            strength_components=getattr(
                medicine,
                "strength_components",
                None,
            ),
            strength_unit=medicine.strength_unit,
            dose_value=medicine.dose_value,
            dose_unit=medicine.dose_unit,
            daily_dose_value=(
                medicine.daily_dose_value
            ),
            daily_dose_unit=(
                medicine.daily_dose_unit
            ),
            daily_dose_components=getattr(
                medicine,
                "daily_dose_components",
                None,
            ),
            route=medicine.route,
            frequency_value=(
                medicine.frequency_value
            ),
            frequency_unit=(
                medicine.frequency_unit
            ),
            duration_value=(
                medicine.duration_value
            ),
            duration_unit=(
                medicine.duration_unit
            ),
            instructions=medicine.instructions,
            extraction_confidence=(
                medicine.extraction_confidence
            ),
            normalization_confidence=(
                medicine.normalization_confidence
            ),
        )

        db_prescription.medicines.append(
            db_medicine
        )

    try:
        db.add(db_prescription)

        # Increment usage inside the same transaction so the
        # counter only moves when the prescription is saved.
        increment_prescription_usage(
            organization_id=current_user.organization_id,
            db=db,
        )

        db.commit()
        db.refresh(db_prescription)

    except HTTPException:
        db.rollback()
        raise

    except Exception as exc:
        db.rollback()

        logger.exception("Failed to save prescription: %s", exc)

        raise HTTPException(
            status_code=500,
            detail="An internal error occurred. Please try again or contact support.",
        )

    return db_prescription


# =========================================================
# UPLOAD PRESCRIPTION IMAGE
# =========================================================


@app.post(
    "/prescriptions/upload",
    response_model=PrescriptionUploadResponse,
    tags=["Prescriptions"],
)
async def upload_prescription(
    file: UploadFile = File(...),
    current_user: UserDB = Depends(
        require_pharmacy_staff
    ),
    db: Session = Depends(get_db),
):
    """
    Upload and analyze a prescription image.

    Only pharmacy staff can upload prescriptions.

    The uploaded prescription automatically belongs
    to the pharmacist's organization.
    """

    if not current_user.organization_id:
        raise HTTPException(
            status_code=403,
            detail=(
                "Pharmacist is not associated "
                "with an organization"
            ),
        )

    # ---------------------------------------------------
    # Server-side usage limit check.
    # Runs before file I/O to avoid wasted processing.
    # ---------------------------------------------------
    check_prescription_limit(
        organization_id=current_user.organization_id,
        db=db,
    )

    allowed_types = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/jpg": ".jpg",
    }

    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=(
                "Only JPG and PNG files are supported. "
                f"Received: {file.content_type}"
            ),
        )

    extension = allowed_types[
        file.content_type
    ]

    file_id = uuid4()

    stored_filename = (
        f"{file_id}{extension}"
    )

    file_path = (
        UPLOAD_DIR
        / stored_filename
    )

    contents = await file.read()

    if not contents:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is empty",
        )

    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                "File exceeds maximum allowed "
                "size of "
                f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB"
            ),
        )

    # -----------------------------------------------------
    # Magic-byte validation
    #
    # Validate actual file signature BEFORE writing to disk.
    # The client-supplied Content-Type is only used for the
    # allowed-types check above; this check inspects bytes.
    #
    # JPEG:  FF D8 FF
    # PNG:   89 50 4E 47  (‰PNG)
    # -----------------------------------------------------

    _MAGIC_JPEG = b"\xff\xd8\xff"
    _MAGIC_PNG = b"\x89PNG"

    if not (
        contents[:3] == _MAGIC_JPEG
        or contents[:4] == _MAGIC_PNG
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "File content does not match a supported image format. "
                "Only JPEG and PNG files are accepted."
            ),
        )

    # -----------------------------------------------------
    # Save image
    # -----------------------------------------------------

    try:
        with open(
            file_path,
            "wb",
        ) as buffer:
            buffer.write(contents)

    except Exception as exc:
        logger.exception("Failed to save uploaded file: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred. Please try again or contact support.",
        )

    # -----------------------------------------------------
    # Validate image
    # -----------------------------------------------------

    try:
        image = Image.open(
            file_path
        )

        image.load()

    except Exception as exc:
        file_path.unlink(
            missing_ok=True
        )

        logger.warning("Invalid or corrupted image file: %s", exc)
        raise HTTPException(
            status_code=400,
            detail="The uploaded file is not a valid image.",
        )

    # -----------------------------------------------------
    # OCR
    # -----------------------------------------------------

    try:
        raw_text = extract_text_from_image(
            image
        )

    except Exception as exc:
        logger.exception("OCR processing error: %s", exc)

        raise HTTPException(
            status_code=500,
            detail="An internal error occurred. Please try again or contact support.",
        )

    # =====================================================
    # OCR FAILURE
    # =====================================================

    if not raw_text or not raw_text.strip():
        prescription_id = (
            f"RX-{file_id.hex[:8].upper()}"
        )

        db_prescription = PrescriptionDB(
            prescription_id=prescription_id,
            raw_text="",
            status="ocr_failed",
            file_name=file.filename,
            file_path=str(file_path),
            file_type=file.content_type,
            organization_id=(
                current_user.organization_id
            ),
            uploaded_by_id=current_user.id,
            safety_flags=[
                {
                    "type": "ocr_empty",
                    "severity": "error",
                    "medicine": None,
                    "message": (
                        "OCR could not extract any "
                        "text from this image. "
                        "Please upload a clearer, "
                        "well-lit image."
                    ),
                }
            ],
        )

        try:
            db.add(db_prescription)
            db.commit()
            db.refresh(db_prescription)

        except Exception as exc:
            db.rollback()
            logger.exception("Failed to save OCR failure record: %s", exc)
            raise HTTPException(
                status_code=500,
                detail="An internal error occurred. Please try again or contact support.",
            )

        return {
            "message": (
                "Prescription uploaded but OCR "
                "could not extract any text. "
                "Please review the image quality."
            ),
            "prescription_id": prescription_id,
            "file_name": file.filename,
            "file_type": file.content_type,
            "status": "ocr_failed",
            "raw_text": "",
            "medicines": [],
            "safety_flags": (
                db_prescription.safety_flags
            ),
            "analysis_metadata": {
                "ocr_quality": "failed",
                "ocr_text_length": 0,
                "medicine_count": 0,
                "needs_review": True,
            },
        }

    # =====================================================
    # PRESCRIPTION INTELLIGENCE PIPELINE
    # =====================================================

    try:
        analysis = process_prescription(
            raw_text
        )

    except Exception as exc:
        logger.exception("Prescription pipeline error: %s", exc)

        raise HTTPException(
            status_code=500,
            detail="An internal error occurred. Please try again or contact support.",
        )

    medicines = analysis.get(
        "medicines",
        [],
    )

    safety_flags = analysis.get(
        "safety_flags",
        [],
    )

    analysis_metadata = analysis.get(
        "analysis_metadata",
        {},
    )

    interpretation = analysis.get(
        "interpretation",
        {},
    )

    prescription_plan = analysis.get(
        "prescription_plan",
        {},
    )

    safety_analysis = analysis.get(
        "safety_analysis",
        {},
    )

    prescription_id = (
        f"RX-{file_id.hex[:8].upper()}"
    )

    db_prescription = PrescriptionDB(
        prescription_id=prescription_id,
        raw_text=raw_text,
        status="analyzed",
        file_name=file.filename,
        file_path=str(file_path),
        file_type=file.content_type,
        organization_id=(
            current_user.organization_id
        ),
        uploaded_by_id=current_user.id,
        safety_flags=safety_flags,
    )

    # -----------------------------------------------------
    # Store medicines
    # -----------------------------------------------------

    for medicine in medicines:
        strength_value = medicine.get(
            "strength_value"
        )

        if strength_value is not None:
            strength_value = str(
                strength_value
            )

        db_medicine = MedicineDB(
            name=medicine.get("name"),
            generic_name=medicine.get(
                "generic_name"
            ),
            brand_name=medicine.get(
                "brand_name"
            ),
            strength_value=strength_value,
            strength_unit=medicine.get(
                "strength_unit"
            ),
            strength_components=(
                medicine.get(
                    "strength_components"
                )
                or []
            ),
            dose_value=medicine.get(
                "dose_value"
            ),
            dose_unit=medicine.get(
                "dose_unit"
            ),
            daily_dose_value=medicine.get(
                "daily_dose_value"
            ),
            daily_dose_unit=medicine.get(
                "daily_dose_unit"
            ),
            daily_dose_components=(
                medicine.get(
                    "daily_dose_components"
                )
                or []
            ),
            route=medicine.get(
                "route"
            ),
            frequency_value=medicine.get(
                "frequency_value"
            ),
            frequency_unit=medicine.get(
                "frequency_unit"
            ),
            duration_value=medicine.get(
                "duration_value"
            ),
            duration_unit=medicine.get(
                "duration_unit"
            ),
            instructions=medicine.get(
                "instructions"
            ),
            extraction_confidence=medicine.get(
                "extraction_confidence"
            ),
            normalization_confidence=medicine.get(
                "normalization_confidence"
            ),
        )

        db_prescription.medicines.append(
            db_medicine
        )

    # -----------------------------------------------------
    # Save
    # -----------------------------------------------------

    try:
        db.add(db_prescription)

        # Increment usage counter inside the same transaction
        # so usage is only recorded when the upload succeeds.
        if current_user.organization_id:
            increment_prescription_usage(
                organization_id=current_user.organization_id,
                db=db,
            )

        db.commit()
        db.refresh(db_prescription)

    except HTTPException:
        db.rollback()
        raise

    except Exception as exc:
        db.rollback()

        logger.exception("Failed to save analyzed prescription: %s", exc)

        raise HTTPException(
            status_code=500,
            detail="An internal error occurred. Please try again or contact support.",
        )

    if medicines:
        message = (
            "Prescription uploaded and analyzed "
            "successfully"
        )
    else:
        message = (
            "Prescription uploaded, but no medicines "
            "could be reliably extracted. Manual "
            "verification is required."
        )

    return {
        "message": message,
        "prescription_id": prescription_id,
        "file_name": file.filename,
        "file_type": file.content_type,
        "status": db_prescription.status,
        "raw_text": raw_text,
        "medicines": medicines,
        "safety_flags": safety_flags,
        "analysis_metadata": analysis_metadata,
        "interpretation": interpretation,
        "prescription_plan": prescription_plan,
        "safety_analysis": safety_analysis,
        "evidence_chains": analysis.get("evidence_chains", []),
    }


# =========================================================
# PRESCRIPTION HISTORY
# =========================================================


# Valid review_status values that callers may filter by.
_VALID_REVIEW_STATUSES = {
    "pending",
    "under_review",
    "verified",
    "rejected",
    "needs_clarification",
}

# Valid pipeline status values.
_VALID_PIPELINE_STATUSES = {
    "uploaded",
    "analyzed",
    "ocr_failed",
}


@app.get(
    "/prescriptions",
    response_model=list[PrescriptionResponse],
    tags=["Prescriptions"],
)
def list_prescriptions(
    skip: int = 0,
    limit: int = 20,
    review_status: str | None = None,
    status: str | None = None,
    search: str | None = None,
    current_user: UserDB = Depends(
        require_any_authenticated_user
    ),
    db: Session = Depends(get_db),
):
    """
    List prescriptions according to role.

    Pharmacist:
        Only prescriptions belonging to their pharmacy.

    Customer:
        Only their own prescriptions.

    Admin:
        All prescriptions.

    Optional query parameters (server-side filtering):
        review_status: one of pending|under_review|verified|rejected|needs_clarification
        status: pipeline status – uploaded|analyzed|ocr_failed
        search: case-insensitive substring match against prescription_id and file_name
    """

    if skip < 0:
        raise HTTPException(
            status_code=400,
            detail="skip cannot be negative",
        )

    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code=400,
            detail="limit must be between 1 and 100",
        )

    if review_status is not None and review_status not in _VALID_REVIEW_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid review_status '{review_status}'. "
                f"Allowed values: {', '.join(sorted(_VALID_REVIEW_STATUSES))}"
            ),
        )

    if status is not None and status not in _VALID_PIPELINE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid status '{status}'. "
                f"Allowed values: {', '.join(sorted(_VALID_PIPELINE_STATUSES))}"
            ),
        )

    query = (
        db.query(PrescriptionDB)
        .options(
            selectinload(
                PrescriptionDB.medicines
            ),
            selectinload(
                PrescriptionDB.customer
            ),
        )
    )

    # -----------------------------------------------------
    # Tenant / role scope
    # -----------------------------------------------------

    if current_user.role == "pharmacist":
        if not current_user.organization_id:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Pharmacist is not associated "
                    "with an organization"
                ),
            )

        query = query.filter(
            PrescriptionDB.organization_id
            == current_user.organization_id
        )

    elif current_user.role == "customer":
        customer = (
            db.query(CustomerDB)
            .filter(
                CustomerDB.user_id
                == current_user.id
            )
            .first()
        )

        if not customer:
            return []

        query = query.filter(
            PrescriptionDB.customer_id
            == customer.id
        )

    elif current_user.role == "admin":
        pass

    else:
        raise HTTPException(
            status_code=403,
            detail="Unsupported user role",
        )

    # -----------------------------------------------------
    # Optional server-side filters
    # -----------------------------------------------------

    if review_status is not None:
        # "pending" is stored as NULL or the literal string "pending"
        # in legacy rows — handle both.
        if review_status == "pending":
            from sqlalchemy import or_
            query = query.filter(
                or_(
                    PrescriptionDB.review_status == "pending",
                    PrescriptionDB.review_status.is_(None),
                )
            )
        else:
            query = query.filter(
                PrescriptionDB.review_status == review_status
            )

    if status is not None:
        query = query.filter(
            PrescriptionDB.status == status
        )

    if search is not None:
        term = search.strip()
        if term:
            pattern = f"%{term}%"
            query = query.filter(
                PrescriptionDB.prescription_id.ilike(pattern)
                | PrescriptionDB.file_name.ilike(pattern)
            )

    return (
        query
        .order_by(
            PrescriptionDB.created_at.desc()
        )
        .offset(skip)
        .limit(limit)
        .all()
    )


# =========================================================
# GENERATE PRESCRIPTION PDF REPORT
# =========================================================


@app.get(
    "/prescriptions/{prescription_id}/report",
    tags=["Prescriptions"],
)
def download_prescription_report(
    prescription_id: str,
    current_user: UserDB = Depends(
        require_any_authenticated_user
    ),
    db: Session = Depends(get_db),
):
    """
    Generate a PDF intelligence report.

    Access is restricted according to user role.

    The report combines:
        - existing prescription intelligence
        - OCR evidence
        - medication safety findings
        - stored pharmacist review status
        - immutable pharmacist review audit history
    """

    prescription = (
        db.query(PrescriptionDB)
        .options(
            selectinload(
                PrescriptionDB.medicines
            )
        )
        .filter(
            PrescriptionDB.prescription_id
            == prescription_id
        )
        .first()
    )

    if not prescription:
        raise HTTPException(
            status_code=404,
            detail="Prescription not found",
        )

    _ensure_prescription_access(
        prescription=prescription,
        current_user=current_user,
        db=db,
    )

    # ---------------------------------------------------------
    # Plan entitlement check.
    #
    # PDF reports are a paid feature.  Pharmacists on plans where
    # pdf_reports_enabled=False receive HTTP 403.
    #
    # Customers and admins are exempt:
    #   - Customers view their own prescriptions; the pharmacy's
    #     plan governs the analysis, not the patient's access.
    #   - Admins have platform-wide access.
    # ---------------------------------------------------------
    if current_user.role == "pharmacist":
        if not current_user.organization_id:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Pharmacist is not associated "
                    "with an organization"
                ),
            )

        plan = get_plan_status(
            organization_id=current_user.organization_id,
            db=db,
        )

        if not plan.get("pdf_reports_enabled", False):
            raise HTTPException(
                status_code=403,
                detail=(
                    "PDF reports are not available on your current plan. "
                    "Please contact support to upgrade."
                ),
            )

    raw_text = (
        prescription.raw_text
        or ""
    )

    # -----------------------------------------------------
    # Rebuild the existing intelligence report
    # -----------------------------------------------------

    if raw_text.strip():
        try:
            analysis = process_prescription(
                raw_text
            )

        except Exception as exc:
            logger.exception(
                "Failed to rebuild prescription analysis "
                "for PDF report %s",
                prescription_id,
            )

            raise HTTPException(
                status_code=500,
                detail=(
                    "Unable to generate prescription "
                    "analysis for the report."
                ),
            ) from exc

        analysis_metadata = analysis.get(
            "analysis_metadata",
            {},
        )

        interpretation = analysis.get(
            "interpretation",
            {},
        )

        prescription_plan = analysis.get(
            "prescription_plan",
            {},
        )

        safety_analysis = analysis.get(
            "safety_analysis",
            {},
        )

    else:
        analysis_metadata = {
            "ocr_quality": "failed",
            "ocr_text_length": 0,
            "medicine_count": 0,
            "needs_review": True,
        }

        interpretation = {
            "status": "review_required",
            "medicines": [],
        }

        prescription_plan = {
            "status": "review_required",
            "medicines": [],
        }

        safety_analysis = {
            "safety_status": "review_required",
            "overall_status": "review_required",
            "confidence": 0.0,
            "medicines": [],
            "prescription_issues": [
                {
                    "type": "ocr_empty",
                    "severity": "error",
                    "medicine": None,
                    "title": "OCR extraction failed",
                    "message": (
                        "OCR could not extract any "
                        "prescription text. Manual "
                        "verification is required."
                    ),
                }
            ],
        }

    # -----------------------------------------------------
    # Load pharmacist review state
    # -----------------------------------------------------

    review_status = (
        prescription.review_status
        or "pending"
    )

    reviewer = None

    if prescription.reviewed_by:
        reviewer = {
            "id": str(
                prescription.reviewed_by.id
            ),
            "name": prescription.reviewed_by.name,
            "email": prescription.reviewed_by.email,
            "role": prescription.reviewed_by.role,
        }

    # -----------------------------------------------------
    # Load immutable review audit history
    # -----------------------------------------------------

    audits = (
        db.query(ReviewAuditDB)
        .filter(
            ReviewAuditDB.prescription_id
            == prescription.id
        )
        .order_by(
            ReviewAuditDB.created_at.asc(),
            ReviewAuditDB.id.asc(),
        )
        .all()
    )

    review_audits = []

    for audit in audits:
        audit_reviewer_name = None

        if audit.reviewer:
            audit_reviewer_name = (
                audit.reviewer.name
            )

        review_audits.append(
            {
                "id": str(audit.id),
                "action": audit.action,
                "previous_status": (
                    audit.previous_status
                ),
                "new_status": (
                    audit.new_status
                ),
                "finding_type": (
                    audit.finding_type
                ),
                "finding_data": (
                    audit.finding_data
                ),
                "note": audit.note,
                "reviewer_id": (
                    str(audit.reviewer_id)
                    if audit.reviewer_id is not None
                    else None
                ),
                "reviewer_name": (
                    audit_reviewer_name
                ),
                "created_at": (
                    audit.created_at
                ),
            }
        )

    # -----------------------------------------------------
    # Build stored review metadata
    # -----------------------------------------------------

    review_metadata = {
        "review_status": review_status,

        "reviewed_by_id": (
            prescription.reviewed_by_id
        ),

        "reviewed_at": (
            prescription.reviewed_at
        ),

        "review_notes": (
            prescription.review_notes
        ),

        "reviewer": reviewer,

        "audits": review_audits,
    }

    # -----------------------------------------------------
    # Build structured report
    # -----------------------------------------------------

    report = build_prescription_report(
        safety_analysis,

        source_medicines=analysis.get(
            "medicines",
            [],
        ) if raw_text.strip() else [],

        prescription_id=(
            prescription.prescription_id
        ),
        file_name=(
            prescription.file_name
        ),
        raw_text=raw_text,
        analysis_metadata=(
            analysis_metadata
        ),
        interpretation=(
            interpretation
        ),
        prescription_plan=(
            prescription_plan
        ),
        review_metadata=(
            review_metadata
        ),
    )

    # -----------------------------------------------------
    # Generate PDF
    # -----------------------------------------------------

    try:
        pdf_bytes = generate_prescription_pdf(
            report
        )

    except Exception as exc:
        logger.exception(
            "Failed to generate prescription PDF "
            "for %s",
            prescription_id,
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to generate prescription report."
            ),
        ) from exc

    filename = (
        f"{prescription.prescription_id}"
        "-prescription-intelligence-report.pdf"
    )

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}"'
            )
        },
    )


# =========================================================
# PRESCRIPTION IMAGE (authenticated)
# =========================================================


@app.get(
    "/prescriptions/{prescription_id}/image",
    tags=["Prescriptions"],
)
def get_prescription_image(
    prescription_id: str,
    current_user: UserDB = Depends(
        require_any_authenticated_user
    ),
    db: Session = Depends(get_db),
):
    """
    Serve the uploaded prescription image.

    Authorization is required. The file is resolved
    exclusively from the prescription's server-side
    file_path record — the client never supplies a path.
    """

    prescription = (
        db.query(PrescriptionDB)
        .filter(
            PrescriptionDB.prescription_id
            == prescription_id
        )
        .first()
    )

    if not prescription:
        raise HTTPException(
            status_code=404,
            detail="Prescription not found",
        )

    _ensure_prescription_access(
        prescription=prescription,
        current_user=current_user,
        db=db,
    )

    if not prescription.file_path:
        raise HTTPException(
            status_code=404,
            detail="Prescription image not available",
        )

    # --------------------------------------------------
    # Resolve the stored path and guard against traversal.
    #
    # prescription.file_path is an absolute path written
    # by the server at upload time. We resolve it and
    # verify it is inside UPLOAD_DIR before serving.
    # --------------------------------------------------

    try:
        image_path = Path(
            prescription.file_path
        ).resolve()
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=404,
            detail="Prescription image not available",
        )

    upload_dir_resolved = UPLOAD_DIR.resolve()

    if not str(image_path).startswith(
        str(upload_dir_resolved)
    ):
        raise HTTPException(
            status_code=404,
            detail="Prescription image not available",
        )

    if not image_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Prescription image not available",
        )

    media_type = (
        prescription.file_type
        or "application/octet-stream"
    )

    return FileResponse(
        path=str(image_path),
        media_type=media_type,
    )


# =========================================================
# ASSIGN CUSTOMER TO PRESCRIPTION
# =========================================================


@app.patch(
    "/prescriptions/{prescription_id}/customer",
    tags=["Prescriptions"],
)
def assign_prescription_customer(
    prescription_id: str,
    request: PrescriptionCustomerAssignRequest,
    current_user: UserDB = Depends(
        require_pharmacy_staff
    ),
    db: Session = Depends(get_db),
):
    """
    Assign an existing customer to a prescription.

    Only pharmacy staff can perform this operation.

    The prescription and customer must both belong
    to the pharmacist's organization.

    Admin users can assign customers across organizations.
    """

    # -----------------------------------------------------
    # Find prescription
    # -----------------------------------------------------

    prescription = (
        db.query(PrescriptionDB)
        .filter(
            PrescriptionDB.prescription_id
            == prescription_id
        )
        .first()
    )

    if not prescription:
        raise HTTPException(
            status_code=404,
            detail="Prescription not found",
        )

    # -----------------------------------------------------
    # Determine pharmacist organization
    # -----------------------------------------------------

    organization = current_user.organization

    if (
        current_user.role != "admin"
        and organization is None
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Pharmacy organization is required"
            ),
        )

    # -----------------------------------------------------
    # Prescription organization access
    # -----------------------------------------------------

    if current_user.role != "admin":
        if (
            prescription.organization_id
            != organization.id
        ):
            raise HTTPException(
                status_code=404,
                detail="Prescription not found",
            )

    # -----------------------------------------------------
    # Find customer
    # -----------------------------------------------------

    customer = (
        db.query(CustomerDB)
        .filter(
            CustomerDB.id
            == request.customer_id
        )
        .first()
    )

    if not customer:
        raise HTTPException(
            status_code=404,
            detail="Customer not found",
        )

    # -----------------------------------------------------
    # Customer organization access
    # -----------------------------------------------------

    if current_user.role != "admin":
        if not customer_belongs_to_organization(
            customer.id,
            organization.id,
            db,
        ):
            raise HTTPException(
                status_code=403,
                detail=(
                    "Customer is not linked "
                    "to this pharmacy"
                ),
            )

    # -----------------------------------------------------
    # Assign customer
    # -----------------------------------------------------

    prescription.customer_id = customer.id

    db.commit()
    db.refresh(prescription)

    return {
        "message": (
            "Customer assigned to prescription "
            "successfully"
        ),
        "prescription_id": (
            prescription.prescription_id
        ),
        "customer": {
            "id": str(customer.id),
            "customer_code": (
                customer.customer_code
            ),
            "name": customer.name,
        },
    }


# =========================================================
# GET PRESCRIPTION BY ID
# =========================================================


@app.get(
    "/prescriptions/{prescription_id}",
    response_model=PrescriptionResponse,
    tags=["Prescriptions"],
)
def get_prescription(
    prescription_id: str,
    current_user: UserDB = Depends(
        require_any_authenticated_user
    ),
    db: Session = Depends(get_db),
):
    """
    Get one prescription.

    Access is restricted according to role.
    """

    prescription = (
        db.query(PrescriptionDB)
        .options(
            selectinload(
                PrescriptionDB.medicines
            ),
            selectinload(
                PrescriptionDB.customer
            ),
        )
        .filter(
            PrescriptionDB.prescription_id
            == prescription_id
        )
        .first()
    )

    if not prescription:
        raise HTTPException(
            status_code=404,
            detail="Prescription not found",
        )

    _ensure_prescription_access(
        prescription=prescription,
        current_user=current_user,
        db=db,
    )

    return prescription


# =========================================================
# MEDICINE LOOKUP
# =========================================================


@app.get(
    "/medicines/lookup",
    tags=["Medicines"],
)
def lookup_medicine(
    q: str,
    current_user: UserDB = Depends(
        require_any_authenticated_user
    ),
    db: Session = Depends(get_db),
):
    """
    Look up medicines.

    Pharmacists:
        Medicines from their organization's prescriptions.

    Customers:
        Medicines from their own prescriptions.

    Admin:
        All medicines.
    """

    if not q or len(q.strip()) < 2:
        raise HTTPException(
            status_code=400,
            detail=(
                "Search query must be at least "
                "2 characters"
            ),
        )

    query = (
        db.query(MedicineDB)
        .join(
            PrescriptionDB,
            MedicineDB.prescription_id
            == PrescriptionDB.id,
        )
    )

    # -----------------------------------------------------
    # Pharmacist
    # -----------------------------------------------------

    if current_user.role == "pharmacist":
        if not current_user.organization_id:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Pharmacist is not associated "
                    "with an organization"
                ),
            )

        query = query.filter(
            PrescriptionDB.organization_id
            == current_user.organization_id
        )

    # -----------------------------------------------------
    # Customer
    # -----------------------------------------------------

    elif current_user.role == "customer":
        customer = (
            db.query(CustomerDB)
            .filter(
                CustomerDB.user_id
                == current_user.id
            )
            .first()
        )

        if not customer:
            return []

        query = query.filter(
            PrescriptionDB.customer_id
            == customer.id
        )

    # -----------------------------------------------------
    # Admin
    # -----------------------------------------------------

    elif current_user.role == "admin":
        pass

    else:
        raise HTTPException(
            status_code=403,
            detail="Unsupported user role",
        )

    results = (
        query.filter(
            MedicineDB.name.ilike(
                f"%{q.strip()}%"
            )
        )
        .limit(20)
        .all()
    )

    return [
        {
            "name": medicine.name,
            "generic_name": (
                medicine.generic_name
            ),
            "brand_name": (
                medicine.brand_name
            ),
            "strength_value": (
                medicine.strength_value
            ),
            "strength_unit": (
                medicine.strength_unit
            ),
        }
        for medicine in results
    ]


# =========================================================
# PRESCRIPTION ACCESS CONTROL
# =========================================================


def _ensure_prescription_access(
    prescription: PrescriptionDB,
    current_user: UserDB,
    db: Session,
):
    """
    Central authorization check for prescriptions.

    Rules:

        Admin
            → all prescriptions

        Pharmacist
            → prescriptions belonging to
              their organization

        Customer
            → prescriptions belonging to
              their CustomerDB profile
    """

    # -----------------------------------------------------
    # Admin
    # -----------------------------------------------------

    if current_user.role == "admin":
        return

    # -----------------------------------------------------
    # Pharmacist
    # -----------------------------------------------------

    if current_user.role == "pharmacist":
        if (
            not current_user.organization_id
            or prescription.organization_id
            != current_user.organization_id
        ):
            raise HTTPException(
                status_code=404,
                detail="Prescription not found",
            )

        return

    # -----------------------------------------------------
    # Customer
    # -----------------------------------------------------

    if current_user.role == "customer":
        customer = (
            db.query(CustomerDB)
            .filter(
                CustomerDB.user_id
                == current_user.id
            )
            .first()
        )

        if (
            not customer
            or prescription.customer_id
            != customer.id
        ):
            raise HTTPException(
                status_code=404,
                detail="Prescription not found",
            )

        return

    # -----------------------------------------------------
    # Unknown role
    # -----------------------------------------------------

    raise HTTPException(
        status_code=403,
        detail="Unsupported user role",
    )
