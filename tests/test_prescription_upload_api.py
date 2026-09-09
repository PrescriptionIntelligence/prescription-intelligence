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

    client = TestClient(
        app,
        raise_server_exceptions=False,
    )

    yield client

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