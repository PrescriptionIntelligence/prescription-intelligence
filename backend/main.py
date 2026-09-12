import logging
import os
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image
from backend.routers import auth, users
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from backend.database import get_db
from backend.models import PrescriptionDB, MedicineDB
from backend.schemas import (
    PrescriptionCreate,
    PrescriptionResponse,
    PrescriptionUploadResponse,
    DashboardStatsResponse,
)
from backend.services.ocr_service import extract_text_from_image
from backend.services.prescription_pipeline import process_prescription
from backend.services.prescription_report import build_prescription_report
from backend.services.pdf_report_generator import generate_prescription_pdf

logger = logging.getLogger(__name__)

# ---------------------------------------------------------
# Paths
# ---------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent

UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

# ---------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------

app = FastAPI(
    title="Prescription Intelligence API",
    description=(
        "AI-powered prescription intelligence "
        "and medication safety platform"
    ),
    version="1.0.0",
)

app.include_router(auth.router)
app.include_router(users.router)

# Serve uploaded prescription images at /uploads/<filename>
# so the frontend can display the original image.
app.mount(
    "/uploads",
    StaticFiles(directory=str(UPLOAD_DIR)),
    name="uploads",
)

_allowed_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------
# Root
# ---------------------------------------------------------


@app.get("/")
def root():
    return {
        "project": "Prescription Intelligence",
        "status": "running",
        "version": "1.0.0",
    }


# ---------------------------------------------------------
# Health
# ---------------------------------------------------------


@app.get("/health")
def health():
    return {
        "status": "healthy",
    }


# ---------------------------------------------------------
# Dashboard statistics
# ---------------------------------------------------------


@app.get(
    "/dashboard/stats",
    response_model=DashboardStatsResponse,
    tags=["Dashboard"],
)
def get_dashboard_stats(
    db: Session = Depends(get_db),
):
    """
    Return aggregate statistics for the dashboard.
    """

    total_prescriptions = (
        db.query(func.count(PrescriptionDB.id))
        .scalar()
    ) or 0

    total_medicines = (
        db.query(func.count(MedicineDB.id))
        .scalar()
    ) or 0

    # Prescriptions that have at least one safety flag.
    # safety_flags is a JSONB array; use jsonb_array_length for PostgreSQL.
    # Wrapped in a try/except to gracefully handle environments that don't
    # support the jsonb_array_length function (e.g. SQLite in tests).
    try:
        prescriptions_with_flags = (
            db.query(func.count(PrescriptionDB.id))
            .filter(
                PrescriptionDB.safety_flags.isnot(None),
                func.jsonb_array_length(
                    PrescriptionDB.safety_flags
                ) > 0,
            )
            .scalar()
        ) or 0
    except Exception:
        prescriptions_with_flags = 0

    # Prescriptions requiring review = low normalization
    # confidence or any safety flag present.
    needs_review = (
        db.query(func.count(PrescriptionDB.id.distinct()))
        .join(
            MedicineDB,
            MedicineDB.prescription_id == PrescriptionDB.id,
        )
        .filter(
            (MedicineDB.normalization_confidence < 0.70)
            | (MedicineDB.extraction_confidence < 0.70)
        )
        .scalar()
    ) or 0

    # 5 most recent prescriptions for the "recent" list
    recent = (
        db.query(PrescriptionDB)
        .options(selectinload(PrescriptionDB.medicines))
        .order_by(PrescriptionDB.created_at.desc())
        .limit(5)
        .all()
    )

    recent_list = []

    for rx in recent:
        medicine_count = len(rx.medicines)
        safety_count = len(rx.safety_flags or [])

        # Compute a simple confidence summary from medicines
        confidences = [
            m.normalization_confidence
            for m in rx.medicines
            if m.normalization_confidence is not None
        ]

        avg_confidence = (
            round(sum(confidences) / len(confidences), 2)
            if confidences
            else None
        )

        recent_list.append({
            "prescription_id": rx.prescription_id,
            "file_name": rx.file_name,
            "created_at": rx.created_at.isoformat(),
            "status": rx.status,
            "medicine_count": medicine_count,
            "safety_count": safety_count,
            "avg_confidence": avg_confidence,
        })

    return {
        "total_prescriptions": total_prescriptions,
        "total_medicines": total_medicines,
        "prescriptions_with_alerts": prescriptions_with_flags,
        "needs_review": needs_review,
        "recent_prescriptions": recent_list,
    }


# ---------------------------------------------------------
# Create prescription manually
# ---------------------------------------------------------


@app.post(
    "/prescriptions",
    response_model=PrescriptionResponse,
    status_code=201,
    tags=["Prescriptions"],
)
def create_prescription(
    prescription: PrescriptionCreate,
    db: Session = Depends(get_db),
):
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
        prescription_id=prescription.prescription_id,
        raw_text=prescription.raw_text,
        status="uploaded",
    )

    for medicine in prescription.medicines:
        strength_value = medicine.strength_value

        if strength_value is not None:
            strength_value = str(strength_value)

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
            daily_dose_value=medicine.daily_dose_value,
            daily_dose_unit=medicine.daily_dose_unit,
            daily_dose_components=getattr(
                medicine,
                "daily_dose_components",
                None,
            ),
            route=medicine.route,
            frequency_value=medicine.frequency_value,
            frequency_unit=medicine.frequency_unit,
            duration_value=medicine.duration_value,
            duration_unit=medicine.duration_unit,
            instructions=medicine.instructions,
            extraction_confidence=(
                medicine.extraction_confidence
            ),
            normalization_confidence=(
                medicine.normalization_confidence
            ),
        )

        db_prescription.medicines.append(db_medicine)

    try:
        db.add(db_prescription)
        db.commit()
        db.refresh(db_prescription)

    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to save prescription: "
                f"{str(exc)}"
            ),
        )

    return db_prescription


# ---------------------------------------------------------
# Upload prescription image
# ---------------------------------------------------------


@app.post(
    "/prescriptions/upload",
    response_model=PrescriptionUploadResponse,
    tags=["Prescriptions"],
)
async def upload_prescription(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
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

    extension = allowed_types[file.content_type]

    file_id = uuid4()
    stored_filename = f"{file_id}{extension}"
    file_path = UPLOAD_DIR / stored_filename

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
                f"File exceeds maximum allowed size of "
                f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB"
            ),
        )

    try:
        with open(file_path, "wb") as buffer:
            buffer.write(contents)

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Failed to save uploaded file: {str(exc)}"
            ),
        )

    try:
        image = Image.open(file_path)
        image.load()

    except Exception as exc:
        # Remove the corrupted file
        file_path.unlink(missing_ok=True)

        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid or corrupted image file: {str(exc)}"
            ),
        )

    try:
        raw_text = extract_text_from_image(image)

    except Exception as exc:
        logger.error(
            "OCR processing error: %s",
            exc,
            exc_info=True,
        )

        raise HTTPException(
            status_code=500,
            detail=f"OCR processing failed: {str(exc)}",
        )

    # -----------------------------------------------------
    # OCR failure
    # -----------------------------------------------------

    if not raw_text or not raw_text.strip():
        prescription_id = f"RX-{file_id.hex[:8].upper()}"

        db_prescription = PrescriptionDB(
            prescription_id=prescription_id,
            raw_text="",
            status="ocr_failed",
            file_name=file.filename,
            file_path=str(file_path),
            file_type=file.content_type,
            safety_flags=[
                {
                    "type": "ocr_empty",
                    "severity": "error",
                    "medicine": None,
                    "message": (
                        "OCR could not extract any text from this image. "
                        "Please upload a clearer, well-lit image."
                    ),
                }
            ],
        )

        db.add(db_prescription)
        db.commit()
        db.refresh(db_prescription)

        return {
            "message": (
                "Prescription uploaded but OCR could not extract "
                "any text. Please review the image quality."
            ),
            "prescription_id": prescription_id,
            "file_name": file.filename,
            "file_type": file.content_type,
            "file_path": str(file_path),
            "stored_filename": stored_filename,
            "status": "ocr_failed",
            "raw_text": "",
            "medicines": [],
            "safety_flags": db_prescription.safety_flags,
            "analysis_metadata": {
                "ocr_quality": "failed",
                "ocr_text_length": 0,
                "medicine_count": 0,
                "needs_review": True,
            },
        }

    # -----------------------------------------------------
    # Prescription intelligence pipeline
    # -----------------------------------------------------

    try:
        analysis = process_prescription(raw_text)

    except Exception as exc:
        logger.error(
            "Pipeline error: %s",
            exc,
            exc_info=True,
        )

        raise HTTPException(
            status_code=500,
            detail=(
                f"Prescription processing failed: {str(exc)}"
            ),
        )

    medicines = analysis.get("medicines", [])

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

    prescription_id = f"RX-{file_id.hex[:8].upper()}"

    db_prescription = PrescriptionDB(
        prescription_id=prescription_id,
        raw_text=raw_text,
        status="analyzed",
        file_name=file.filename,
        file_path=str(file_path),
        file_type=file.content_type,
        safety_flags=safety_flags,
    )

    for medicine in medicines:
        strength_value = medicine.get("strength_value")

        if strength_value is not None:
            strength_value = str(strength_value)

        db_medicine = MedicineDB(
            name=medicine.get("name"),
            generic_name=medicine.get("generic_name"),
            brand_name=medicine.get("brand_name"),
            strength_value=strength_value,
            strength_unit=medicine.get("strength_unit"),
            strength_components=(
                medicine.get("strength_components") or []
            ),
            dose_value=medicine.get("dose_value"),
            dose_unit=medicine.get("dose_unit"),
            daily_dose_value=medicine.get(
                "daily_dose_value"
            ),
            daily_dose_unit=medicine.get(
                "daily_dose_unit"
            ),
            daily_dose_components=(
                medicine.get("daily_dose_components") or []
            ),
            route=medicine.get("route"),
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

        db_prescription.medicines.append(db_medicine)

    try:
        db.add(db_prescription)
        db.commit()
        db.refresh(db_prescription)

    except Exception as exc:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Failed to save prescription: {str(exc)}",
        )

    if medicines:
        message = (
            "Prescription uploaded and analyzed successfully"
        )
    else:
        message = (
            "Prescription uploaded, but no medicines could be "
            "reliably extracted. Manual verification is required."
        )

    return {
        "message": message,
        "prescription_id": prescription_id,
        "file_name": file.filename,
        "file_type": file.content_type,
        "file_path": str(file_path),
        "stored_filename": stored_filename,
        "status": db_prescription.status,
        "raw_text": raw_text,
        "medicines": medicines,
        "safety_flags": safety_flags,
        "analysis_metadata": analysis_metadata,
        "interpretation": interpretation,
        "prescription_plan": prescription_plan,
        "safety_analysis": safety_analysis,
    }


# ---------------------------------------------------------
# Prescription history (paginated)
# ---------------------------------------------------------


@app.get(
    "/prescriptions",
    response_model=list[PrescriptionResponse],
    tags=["Prescriptions"],
)
def list_prescriptions(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    prescriptions = (
        db.query(PrescriptionDB)
        .options(selectinload(PrescriptionDB.medicines))
        .order_by(PrescriptionDB.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return prescriptions


# ---------------------------------------------------------
# Generate prescription PDF report
# ---------------------------------------------------------


@app.get(
    "/prescriptions/{prescription_id}/report",
    tags=["Prescriptions"],
)
def download_prescription_report(
    prescription_id: str,
    db: Session = Depends(get_db),
):
    """
    Generate and return a PDF intelligence report for a prescription.

    The report is generated from the stored OCR text so that the same
    prescription intelligence pipeline is used consistently without
    requiring any database schema changes.
    """

    prescription = (
        db.query(PrescriptionDB)
        .options(selectinload(PrescriptionDB.medicines))
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
    # Re-run the intelligence pipeline from stored OCR text
    # -----------------------------------------------------

    raw_text = prescription.raw_text or ""

    if raw_text.strip():
        try:
            analysis = process_prescription(raw_text)

        except Exception as exc:
            logger.error(
                "Report pipeline error for %s: %s",
                prescription_id,
                exc,
                exc_info=True,
            )

            raise HTTPException(
                status_code=500,
                detail=(
                    "Unable to generate the prescription analysis "
                    f"for the report: {str(exc)}"
                ),
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

    else:
        # -------------------------------------------------
        # OCR-failed prescription
        # -------------------------------------------------

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
                        "OCR could not extract any prescription text. "
                        "Manual verification is required."
                    ),
                }
            ],
        }

    # -----------------------------------------------------
    # Build structured report
    # -----------------------------------------------------

    report = build_prescription_report(
        safety_analysis,
        prescription_id=prescription.prescription_id,
        file_name=prescription.file_name,
        raw_text=raw_text,
        analysis_metadata=analysis_metadata,
        interpretation=interpretation,
        prescription_plan=prescription_plan,
    )

    # -----------------------------------------------------
    # Generate PDF
    # -----------------------------------------------------

    try:
        pdf_bytes = generate_prescription_pdf(report)

    except Exception as exc:
        logger.error(
            "PDF generation error for %s: %s",
            prescription_id,
            exc,
            exc_info=True,
        )

        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate PDF report: {str(exc)}",
        )

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


# ---------------------------------------------------------
# Get prescription by ID
# ---------------------------------------------------------


@app.get(
    "/prescriptions/{prescription_id}",
    response_model=PrescriptionResponse,
    tags=["Prescriptions"],
)
def get_prescription(
    prescription_id: str,
    db: Session = Depends(get_db),
):
    prescription = (
        db.query(PrescriptionDB)
        .options(selectinload(PrescriptionDB.medicines))
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

    return prescription


# ---------------------------------------------------------
# Medicine lookup
# ---------------------------------------------------------


@app.get(
    "/medicines/lookup",
    tags=["Medicines"],
)
def lookup_medicine(
    q: str,
    db: Session = Depends(get_db),
):
    """
    Look up medicines by name fragment.
    Returns matching medicines from the analysis history.
    """

    if not q or len(q.strip()) < 2:
        raise HTTPException(
            status_code=400,
            detail="Search query must be at least 2 characters",
        )

    results = (
        db.query(MedicineDB)
        .filter(
            MedicineDB.name.ilike(
                f"%{q.strip()}%"
            )
        )
        .limit(20)
        .all()
    )

    return [
        {
            "name": m.name,
            "generic_name": m.generic_name,
            "brand_name": m.brand_name,
            "strength_value": m.strength_value,
            "strength_unit": m.strength_unit,
        }
        for m in results
    ]