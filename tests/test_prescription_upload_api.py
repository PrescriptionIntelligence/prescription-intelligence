import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base, get_db
from backend.main import app


@pytest.fixture()
def api_client(tmp_path, monkeypatch):
    database_url = "sqlite://"

    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )

    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    monkeypatch.setattr(
        "backend.main.UPLOAD_DIR",
        tmp_path,
    )

    # Test-only authenticated pharmacist.
    #
    # Prescription API tests should exercise prescription/OCR/report
    # behavior, not the authentication implementation. Production
    # authentication remains enabled because this override exists only
    # inside the pytest fixture.
    from types import SimpleNamespace
    from uuid import uuid4

    test_user = SimpleNamespace(
        id=uuid4(),
        name="Test Pharmacist",
        email="test.pharmacist@example.com",
        role="pharmacist",
        organization_id=uuid4(),
        is_active=True,
    )

    # Import the actual authentication dependency used by the API.
    from backend.auth import get_current_user

    app.dependency_overrides[get_current_user] = (
        lambda: test_user
    )

    client = TestClient(
        app,
        raise_server_exceptions=False,
    )

    yield client

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db, None)
    engine.dispose()


def create_test_image() -> bytes:
    image = Image.new(
        "RGB",
        (300, 200),
        "white",
    )

    buffer = io.BytesIO()
    image.save(
        buffer,
        format="PNG",
    )
    buffer.seek(0)

    return buffer.getvalue()


def test_prescription_upload_returns_rich_analysis(
    api_client,
    monkeypatch,
):
    raw_text = (
        "Amoxicillin 500 mg, "
        "1 tablet twice daily for 5 days"
    )

    expected_analysis = {
        "medicines": [
            {
                "name": "Amoxicillin",
                "generic_name": "Amoxicillin",
                "strength_value": 500.0,
                "strength_unit": "mg",
            }
        ],
        "safety_flags": [],
        "analysis_metadata": {
            "needs_review": False,
            "prescription_plan_status": "resolved",
        },
        "interpretation": {
            "status": "accepted",
            "medicine_count": 1,
            "accepted_count": 1,
            "review_required_count": 0,
            "medicines": [],
        },
        "prescription_plan": {
            "status": "resolved",
            "medicine_count": 1,
            "resolved_count": 1,
            "review_required_count": 0,
            "medicines": [],
        },
        "safety_analysis": {
            "safety_status": (
                "no_structural_issues_detected"
            ),
            "medicine_count": 1,
            "issue_count": 0,
            "high_severity_count": 0,
            "medium_severity_count": 0,
            "low_severity_count": 0,
            "medicines": [],
            "prescription_issues": [],
        },
    }

    def fake_ocr(_image):
        return raw_text

    def fake_pipeline(_raw_text):
        assert _raw_text == raw_text
        return expected_analysis

    monkeypatch.setattr(
        "backend.main.extract_text_from_image",
        fake_ocr,
    )

    monkeypatch.setattr(
        "backend.main.process_prescription",
        fake_pipeline,
    )

    response = api_client.post(
        "/prescriptions/upload",
        files={
            "file": (
                "prescription.png",
                create_test_image(),
                "image/png",
            )
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["raw_text"] == raw_text

    assert len(data["medicines"]) == 1

    medicine = data["medicines"][0]

    assert medicine["name"] == "Amoxicillin"
    assert medicine["generic_name"] == "Amoxicillin"
    assert medicine["strength_value"] == 500.0
    assert medicine["strength_unit"] == "mg"

    assert data["safety_flags"] == []

    assert data["analysis_metadata"] == (
        expected_analysis["analysis_metadata"]
    )

    assert data["interpretation"] == (
        expected_analysis["interpretation"]
    )

    assert data["prescription_plan"] == (
        expected_analysis["prescription_plan"]
    )

    assert data["safety_analysis"] == (
        expected_analysis["safety_analysis"]
    )

    assert data["prescription_id"].startswith("RX-")


def test_prescription_upload_ocr_failure_returns_consistent_response(
    api_client,
    monkeypatch,
):
    def fake_ocr(_image):
        return ""

    monkeypatch.setattr(
        "backend.main.extract_text_from_image",
        fake_ocr,
    )

    response = api_client.post(
        "/prescriptions/upload",
        files={
            "file": (
                "empty-prescription.png",
                create_test_image(),
                "image/png",
            )
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "ocr_failed"
    assert data["raw_text"] == ""

    assert data["medicines"] == []

    assert data["analysis_metadata"] == {
        "ocr_quality": "failed",
        "ocr_text_length": 0,
        "medicine_count": 0,
        "needs_review": True,
    }

    assert data["interpretation"] is None
    assert data["prescription_plan"] is None
    assert data["safety_analysis"] is None

    assert data["safety_flags"]

    assert data["safety_flags"][0]["type"] == (
        "ocr_empty"
    )

    assert data["safety_flags"][0]["medicine"] is None


def test_prescription_report_returns_pdf(
    api_client,
    monkeypatch,
):
    raw_text = (
        "Amoxicillin 500 mg, "
        "1 tablet twice daily for 5 days"
    )

    expected_analysis = {
        "medicines": [
            {
                "name": "Amoxicillin",
                "generic_name": "Amoxicillin",
                "strength_value": 500.0,
                "strength_unit": "mg",
                "dose_value": 1.0,
                "dose_unit": "tablet",
                "route": "oral",
                "frequency_value": 2.0,
                "frequency_unit": "daily",
                "duration_value": 5.0,
                "duration_unit": "days",
                "instructions": (
                    "1 tablet twice daily for 5 days"
                ),
                "extraction_confidence": 0.90,
                "normalization_confidence": 0.95,
            }
        ],
        "safety_flags": [],
        "analysis_metadata": {
            "needs_review": False,
            "prescription_plan_status": "resolved",
            "ocr_quality": "good",
            "ocr_text_length": len(raw_text),
            "medicine_count": 1,
        },
        "interpretation": {
            "status": "accepted",
            "medicine_count": 1,
            "accepted_count": 1,
            "review_required_count": 0,
            "medicines": [],
        },
        "prescription_plan": {
            "status": "resolved",
            "medicine_count": 1,
            "resolved_count": 1,
            "review_required_count": 0,
            "medicines": [],
        },
        "safety_analysis": {
            "safety_status": (
                "no_structural_issues_detected"
            ),
            "overall_status": "safe",
            "confidence": 0.95,
            "medicine_count": 1,
            "issue_count": 0,
            "high_severity_count": 0,
            "medium_severity_count": 0,
            "low_severity_count": 0,
            "medicines": [],
            "prescription_issues": [],
        },
    }

    def fake_ocr(_image):
        return raw_text

    def fake_pipeline(_raw_text):
        assert _raw_text == raw_text
        return expected_analysis

    monkeypatch.setattr(
        "backend.main.extract_text_from_image",
        fake_ocr,
    )

    monkeypatch.setattr(
        "backend.main.process_prescription",
        fake_pipeline,
    )

    upload_response = api_client.post(
        "/prescriptions/upload",
        files={
            "file": (
                "prescription.png",
                create_test_image(),
                "image/png",
            )
        },
    )

    assert upload_response.status_code == 200

    prescription_id = upload_response.json()[
        "prescription_id"
    ]

    report_response = api_client.get(
        f"/prescriptions/{prescription_id}/report"
    )

    assert report_response.status_code == 200

    assert report_response.headers[
        "content-type"
    ].startswith("application/pdf")

    assert (
        report_response.headers[
            "content-disposition"
        ].startswith("attachment;")
    )

    assert prescription_id in (
        report_response.headers[
            "content-disposition"
        ]
    )

    assert report_response.content.startswith(
        b"%PDF"
    )

    assert len(report_response.content) > 1000


def test_prescription_report_returns_404_for_unknown_id(
    api_client,
):
    response = api_client.get(
        "/prescriptions/RX-NOT-FOUND/report"
    )

    assert response.status_code == 404

    assert response.json()["detail"] == (
        "Prescription not found"
    )


def test_prescription_report_for_ocr_failed_prescription(
    api_client,
    monkeypatch,
):
    def fake_ocr(_image):
        return ""

    monkeypatch.setattr(
        "backend.main.extract_text_from_image",
        fake_ocr,
    )

    upload_response = api_client.post(
        "/prescriptions/upload",
        files={
            "file": (
                "empty-prescription.png",
                create_test_image(),
                "image/png",
            )
        },
    )

    assert upload_response.status_code == 200

    prescription_id = upload_response.json()[
        "prescription_id"
    ]

    report_response = api_client.get(
        f"/prescriptions/{prescription_id}/report"
    )

    assert report_response.status_code == 200

    assert report_response.headers[
        "content-type"
    ].startswith("application/pdf")

    assert report_response.content.startswith(
        b"%PDF"
    )

    assert len(report_response.content) > 1000