from pathlib import Path
from uuid import uuid4

from PIL import Image
from backend.routers import auth, users
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from sqlalchemy.orm import Session, selectinload

from backend.database import get_db
from backend.models import PrescriptionDB, MedicineDB
from backend.schemas import (
    PrescriptionCreate,
    PrescriptionResponse,
    PrescriptionUploadResponse,
)
from backend.services.ocr_service import extract_text_from_image
from backend.services.prescription_pipeline import process_prescription
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------
# Paths
# ---------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent

UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------

app = FastAPI(
    title="Prescription Intelligence API",
    description=(
        "AI-powered prescription intelligence "
        "and medication safety platform"
    ),
    version="0.1.0",
)

app.include_router(auth.router)
app.include_router(users.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
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
# Create prescription manually
# ---------------------------------------------------------

@app.post(
    "/prescriptions",
    response_model=PrescriptionResponse,
    status_code=201,
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

        # Database stores strength_value as text so that
        # values such as "500", "5", or "3+2" are preserved.
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

        db_prescription.medicines.append(
            db_medicine
        )

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
)
async def upload_prescription(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    allowed_types = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
    }

    # -----------------------------------------------------
    # Validate file type
    # -----------------------------------------------------

    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=(
                "Only JPG and PNG files are currently supported"
            ),
        )

    extension = allowed_types[file.content_type]

    # -----------------------------------------------------
    # Generate storage path
    # -----------------------------------------------------

    file_id = uuid4()

    stored_filename = f"{file_id}{extension}"

    file_path = UPLOAD_DIR / stored_filename

    # -----------------------------------------------------
    # Read uploaded file
    # -----------------------------------------------------

    contents = await file.read()

    if not contents:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is empty",
        )

    # -----------------------------------------------------
    # Save uploaded file
    # -----------------------------------------------------

    try:
        with open(file_path, "wb") as buffer:
            buffer.write(contents)

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to save uploaded file: "
                f"{str(exc)}"
            ),
        )

    # -----------------------------------------------------
    # Open image
    # -----------------------------------------------------

    try:
        image = Image.open(file_path)
        image.load()

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid image file: "
                f"{str(exc)}"
            ),
        )

    # -----------------------------------------------------
    # OCR
    # -----------------------------------------------------

    try:
        raw_text = extract_text_from_image(image)

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "OCR processing failed: "
                f"{str(exc)}"
            ),
        )

    # -----------------------------------------------------
    # Prescription intelligence pipeline
    # -----------------------------------------------------

    try:
        analysis = process_prescription(raw_text)

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Prescription processing failed: "
                f"{str(exc)}"
            ),
        )

    medicines = analysis.get(
        "medicines",
        [],
    )

    safety_flags = analysis.get(
        "safety_flags",
        [],
    )

    # -----------------------------------------------------
    # Generate prescription ID
    # -----------------------------------------------------

    prescription_id = (
        f"RX-{file_id.hex[:8].upper()}"
    )

    # -----------------------------------------------------
    # Create database prescription
    # -----------------------------------------------------

    db_prescription = PrescriptionDB(
        prescription_id=prescription_id,
        raw_text=raw_text,
        status="uploaded",
        file_name=file.filename,
        file_path=str(file_path),
        file_type=file.content_type,
    )

    # -----------------------------------------------------
    # Store extracted medicines
    # -----------------------------------------------------

    for medicine in medicines:

        # -------------------------------------------------
        # Strength
        # -------------------------------------------------

        strength_value = medicine.get(
            "strength_value"
        )

        # Preserve ALL strength representations.
        #
        # Examples:
        #   500
        #   "500"
        #   "3+2"
        #
        # The database column is now String, so we don't
        # discard combination strengths anymore.

        if strength_value is not None:
            strength_value = str(strength_value)

        strength_components = medicine.get(
            "strength_components"
        )

        # -------------------------------------------------
        # Daily dose
        # -------------------------------------------------

        daily_dose_components = medicine.get(
            "daily_dose_components"
        )

        # -------------------------------------------------
        # Create medicine record
        # -------------------------------------------------

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

            strength_components=strength_components,

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

            daily_dose_components=daily_dose_components,

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
    # Save prescription
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # Response message
    # -----------------------------------------------------

    if medicines:
        message = (
            "Prescription uploaded and analyzed successfully"
        )

    else:
        message = (
            "Prescription uploaded, but no medicines "
            "could be reliably extracted. "
            "Manual verification is required."
        )

    # -----------------------------------------------------
    # API response
    # -----------------------------------------------------

    return {
        "message": message,

        "prescription_id": prescription_id,

        "file_name": file.filename,

        "file_type": file.content_type,

        "file_path": str(file_path),

        "status": db_prescription.status,

        "raw_text": raw_text,

        "medicines": medicines,

        "safety_flags": safety_flags,
    }


# ---------------------------------------------------------
# List prescriptions
# ---------------------------------------------------------

@app.get(
    "/prescriptions",
    response_model=list[PrescriptionResponse],
)
def list_prescriptions(
    db: Session = Depends(get_db),
):
    prescriptions = (
        db.query(PrescriptionDB)
        .options(
            selectinload(
                PrescriptionDB.medicines
            )
        )
        .order_by(
            PrescriptionDB.created_at.desc()
        )
        .all()
    )

    return prescriptions


# ---------------------------------------------------------
# Get prescription by ID
# ---------------------------------------------------------

@app.get(
    "/prescriptions/{prescription_id}",
    response_model=PrescriptionResponse,
)
def get_prescription(
    prescription_id: str,
    db: Session = Depends(get_db),
):
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

    return prescription