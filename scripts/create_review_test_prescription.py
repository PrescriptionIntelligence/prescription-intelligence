import sys

from backend.database import SessionLocal
from backend.models import (
    MedicineDB,
    PrescriptionDB,
    ReviewAuditDB,
    UserDB,
)

PRESCRIPTION_ID = "RX-REVIEW-TEST-001"


def main() -> None:
    if len(sys.argv) != 2:
        raise RuntimeError(
            "Usage: python scripts/create_review_test_prescription.py "
            "<pharmacist-email>"
        )

    pharmacist_email = sys.argv[1].strip().lower()

    if not pharmacist_email:
        raise RuntimeError("Pharmacist email cannot be empty.")

    db = SessionLocal()

    try:
        pharmacist = (
            db.query(UserDB)
            .filter(
                UserDB.email == pharmacist_email,
                UserDB.role == "pharmacist",
            )
            .first()
        )

        if pharmacist is None:
            raise RuntimeError(
                f"No pharmacist account found for '{pharmacist_email}'. "
                "Make sure you use the email of the pharmacist account "
                "currently signed in to the frontend."
            )

        if pharmacist.organization_id is None:
            raise RuntimeError(
                f"Pharmacist '{pharmacist_email}' does not belong "
                "to an organization."
            )

        prescription = (
            db.query(PrescriptionDB)
            .filter(
                PrescriptionDB.prescription_id
                == PRESCRIPTION_ID
            )
            .first()
        )

        if prescription is None:
            prescription = PrescriptionDB(
                prescription_id=PRESCRIPTION_ID,
                organization_id=pharmacist.organization_id,
                uploaded_by_id=pharmacist.id,
                status="analyzed",
            )
            db.add(prescription)
            db.flush()

        db.query(ReviewAuditDB).filter(
            ReviewAuditDB.prescription_id == prescription.id
        ).delete(synchronize_session=False)

        db.query(MedicineDB).filter(
            MedicineDB.prescription_id == prescription.id
        ).delete(synchronize_session=False)

        prescription.organization_id = pharmacist.organization_id
        prescription.uploaded_by_id = pharmacist.id
        prescription.customer_id = None
        prescription.status = "analyzed"

        prescription.review_status = "pending"
        prescription.reviewed_by_id = None
        prescription.reviewed_at = None
        prescription.review_notes = None

        prescription.safety_flags = [
            {
                "type": "strength_conflict",
                "severity": "high",
                "message": (
                    "Prescription strength conflicts with "
                    "the resolved medicine reference."
                ),
                "prescription_strength": 10.0,
                "reference_strength": 5.0,
            },
            {
                "type": "drug_interaction",
                "severity": "high",
                "message": (
                    "Potential drug interaction detected."
                ),
            },
            {
                "type": "dose_check",
                "severity": "low",
                "message": "Dose should be verified.",
            },
        ]

        prescription.raw_text = (
            "Warfarin 10 mg\n"
            "Aspirin 75 mg\n"
        )

        prescription.file_name = "review-test-prescription.txt"
        prescription.file_type = "text/plain"

        db.add_all(
            [
                MedicineDB(
                    prescription_id=prescription.id,
                    name="Warfarin",
                    generic_name="Warfarin",
                    brand_name=None,
                    strength_value="10",
                    strength_unit="mg",
                    strength_components=[],
                    dose_value=10.0,
                    dose_unit="mg",
                    daily_dose_value=10.0,
                    daily_dose_unit="mg",
                    daily_dose_components=[],
                    route="oral",
                    frequency_value=1.0,
                    frequency_unit="day",
                    duration_value=None,
                    duration_unit=None,
                    instructions="Take once daily.",
                    extraction_confidence=0.95,
                    normalization_confidence=1.0,
                ),
                MedicineDB(
                    prescription_id=prescription.id,
                    name="Aspirin",
                    generic_name="Aspirin",
                    brand_name=None,
                    strength_value="75",
                    strength_unit="mg",
                    strength_components=[],
                    dose_value=75.0,
                    dose_unit="mg",
                    daily_dose_value=75.0,
                    daily_dose_unit="mg",
                    daily_dose_components=[],
                    route="oral",
                    frequency_value=1.0,
                    frequency_unit="day",
                    duration_value=None,
                    duration_unit=None,
                    instructions="Take once daily.",
                    extraction_confidence=0.95,
                    normalization_confidence=1.0,
                ),
            ]
        )

        db.commit()
        db.refresh(prescription)

        print()
        print("Test prescription created/reset successfully.")
        print(f"Pharmacist: {pharmacist.email}")
        print(f"Organization ID: {pharmacist.organization_id}")
        print(f"Prescription ID: {prescription.prescription_id}")
        print(f"Database ID: {prescription.id}")
        print(f"Review status: {prescription.review_status}")
        print(f"Safety findings: {len(prescription.safety_flags)}")
        print()

    finally:
        db.close()


if __name__ == "__main__":
    main()