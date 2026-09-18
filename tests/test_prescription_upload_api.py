import io
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.auth import get_current_user
from backend.database import Base, get_db
from backend.main import app
from backend.models import OrganizationPlanDB


def _make_engine_and_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )
    Base.metadata.create_all(bind=engine)
    return engine, SessionLocal


def _build_client(tmp_path, monkeypatch, test_user, SessionLocal):
    """Wire up DB, upload dir, and auth overrides; return TestClient."""

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: test_user

    monkeypatch.setattr("backend.main.UPLOAD_DIR", tmp_path)

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def api_client(tmp_path, monkeypatch):
    """
    Pharmacist on a professional plan (pdf_reports_enabled=True).
    Used for upload and report generation tests.
    """
    from types import SimpleNamespace
    from uuid import uuid4

    engine, SessionLocal = _make_engine_and_session()

    org_id = uuid4()
    test_user = SimpleNamespace(
        id=uuid4(),
        name="Test Pharmacist",
        email="test.pharmacist@example.com",
        role="pharmacist",
        organization_id=org_id,
        is_active=True,
    )

    # Insert a professional plan so PDF reports are enabled.
    db = SessionLocal()
    try:
        plan = OrganizationPlanDB(
            organization_id=org_id,
            plan_tier="professional",
            monthly_prescription_limit=500,
            period_start=datetime.now(timezone.utc),
            period_prescription_count=0,
            review_workflow_enabled=True,
            pdf_reports_enabled=True,
        )
        db.add(plan)
        db.commit()
    finally:
        db.close()

    client = _build_client(tmp_path, monkeypatch, test_user, SessionLocal)

    yield client

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db, None)
    engine.dispose()


@pytest.fixture()
def free_plan_client(tmp_path, monkeypatch):
    """
    Pharmacist on a free plan (pdf_reports_enabled=False).
    Used specifically to test PDF entitlement enforcement.
    """
    from types import SimpleNamespace
    from uuid import uuid4

    engine, SessionLocal = _make_engine_and_session()

    org_id = uuid4()
    test_user = SimpleNamespace(
        id=uuid4(),
        name="Free Pharmacist",
        email="free.pharmacist@example.com",
        role="pharmacist",
        organization_id=org_id,
        is_active=True,
    )

    # Insert a free plan with pdf disabled.
    db = SessionLocal()
    try:
        plan = OrganizationPlanDB(
            organization_id=org_id,
            plan_tier="free",
            monthly_prescription_limit=25,
            period_start=datetime.now(timezone.utc),
            period_prescription_count=0,
            review_workflow_enabled=True,
            pdf_reports_enabled=False,
        )
        db.add(plan)
        db.commit()
    finally:
        db.close()

    client = _build_client(tmp_path, monkeypatch, test_user, SessionLocal)

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


# =========================================================
# P0 TESTS: Manual prescription quota enforcement
# =========================================================

def _make_minimal_prescription_payload(prescription_id: str) -> dict:
    """Minimal valid manual-creation payload."""
    return {
        "prescription_id": prescription_id,
        "raw_text": "Test prescription",
        "medicines": [],
    }


def test_manual_creation_under_quota_succeeds(tmp_path, monkeypatch):
    """Manual prescription creation under quota returns 201."""
    from types import SimpleNamespace
    from uuid import uuid4
    from datetime import datetime, timezone

    engine, SessionLocal = _make_engine_and_session()

    org_id = uuid4()
    test_user = SimpleNamespace(
        id=uuid4(),
        name="Quota Test Pharmacist",
        email="quota-test@example.com",
        role="pharmacist",
        organization_id=org_id,
        is_active=True,
    )

    db = SessionLocal()
    try:
        plan = OrganizationPlanDB(
            organization_id=org_id,
            plan_tier="free",
            monthly_prescription_limit=25,
            period_start=datetime.now(timezone.utc),
            period_prescription_count=10,  # Well under limit
            review_workflow_enabled=True,
            pdf_reports_enabled=False,
        )
        db.add(plan)
        db.commit()
    finally:
        db.close()

    client = _build_client(tmp_path, monkeypatch, test_user, SessionLocal)

    try:
        response = client.post(
            "/prescriptions",
            json=_make_minimal_prescription_payload("RX-QUOTA-OK-001"),
        )
        assert response.status_code == 201
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def test_manual_creation_at_quota_returns_429(tmp_path, monkeypatch):
    """Manual prescription creation at quota returns HTTP 429."""
    from types import SimpleNamespace
    from uuid import uuid4
    from datetime import datetime, timezone

    engine, SessionLocal = _make_engine_and_session()

    org_id = uuid4()
    test_user = SimpleNamespace(
        id=uuid4(),
        name="At Limit Pharmacist",
        email="at-limit@example.com",
        role="pharmacist",
        organization_id=org_id,
        is_active=True,
    )

    db = SessionLocal()
    try:
        plan = OrganizationPlanDB(
            organization_id=org_id,
            plan_tier="free",
            monthly_prescription_limit=25,
            period_start=datetime.now(timezone.utc),
            period_prescription_count=25,  # At limit
            review_workflow_enabled=True,
            pdf_reports_enabled=False,
        )
        db.add(plan)
        db.commit()
    finally:
        db.close()

    client = _build_client(tmp_path, monkeypatch, test_user, SessionLocal)

    try:
        response = client.post(
            "/prescriptions",
            json=_make_minimal_prescription_payload("RX-OVER-LIMIT-001"),
        )
        assert response.status_code == 429
        assert "limit" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def test_manual_creation_quota_is_per_organization(tmp_path, monkeypatch):
    """Quota reached in Org A does not affect Org B."""
    from types import SimpleNamespace
    from uuid import uuid4
    from datetime import datetime, timezone

    engine, SessionLocal = _make_engine_and_session()

    org_a = uuid4()
    org_b = uuid4()

    db = SessionLocal()
    try:
        # Org A at limit
        plan_a = OrganizationPlanDB(
            organization_id=org_a,
            plan_tier="free",
            monthly_prescription_limit=25,
            period_start=datetime.now(timezone.utc),
            period_prescription_count=25,
            review_workflow_enabled=True,
            pdf_reports_enabled=False,
        )
        # Org B well under limit
        plan_b = OrganizationPlanDB(
            organization_id=org_b,
            plan_tier="free",
            monthly_prescription_limit=25,
            period_start=datetime.now(timezone.utc),
            period_prescription_count=0,
            review_workflow_enabled=True,
            pdf_reports_enabled=False,
        )
        db.add_all([plan_a, plan_b])
        db.commit()
    finally:
        db.close()

    # Org B pharmacist
    user_b = SimpleNamespace(
        id=uuid4(),
        name="Org B Pharmacist",
        email="org-b@example.com",
        role="pharmacist",
        organization_id=org_b,
        is_active=True,
    )

    client = _build_client(tmp_path, monkeypatch, user_b, SessionLocal)

    try:
        response = client.post(
            "/prescriptions",
            json=_make_minimal_prescription_payload("RX-ORG-B-001"),
        )
        # Org B is unaffected by Org A being at limit
        assert response.status_code == 201
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def test_manual_creation_rejected_does_not_increment_usage(tmp_path, monkeypatch):
    """Usage counter must not increment when a 429 is returned."""
    from types import SimpleNamespace
    from uuid import uuid4
    from datetime import datetime, timezone
    from backend.models import OrganizationPlanDB as PlanDB

    engine, SessionLocal = _make_engine_and_session()

    org_id = uuid4()
    test_user = SimpleNamespace(
        id=uuid4(),
        name="No Increment Pharmacist",
        email="no-increment@example.com",
        role="pharmacist",
        organization_id=org_id,
        is_active=True,
    )

    db = SessionLocal()
    try:
        plan = OrganizationPlanDB(
            organization_id=org_id,
            plan_tier="free",
            monthly_prescription_limit=25,
            period_start=datetime.now(timezone.utc),
            period_prescription_count=25,  # At limit
            review_workflow_enabled=True,
            pdf_reports_enabled=False,
        )
        db.add(plan)
        db.commit()
    finally:
        db.close()

    client = _build_client(tmp_path, monkeypatch, test_user, SessionLocal)

    try:
        response = client.post(
            "/prescriptions",
            json=_make_minimal_prescription_payload("RX-NO-INCREMENT-001"),
        )
        assert response.status_code == 429

        # Verify counter was NOT incremented
        db = SessionLocal()
        try:
            plan_row = db.query(PlanDB).filter(
                PlanDB.organization_id == org_id
            ).first()
            assert plan_row is not None
            assert plan_row.period_prescription_count == 25
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


# =========================================================
# P0 TESTS: PDF report entitlement
# =========================================================


def _upload_prescription_for_report(client, monkeypatch):
    """Helper: upload a prescription and return its ID."""
    raw_text = "Amoxicillin 500 mg, 1 tablet twice daily for 5 days"

    analysis = {
        "medicines": [{"name": "Amoxicillin", "generic_name": "Amoxicillin",
                        "strength_value": 500.0, "strength_unit": "mg"}],
        "safety_flags": [],
        "analysis_metadata": {"needs_review": False, "prescription_plan_status": "resolved"},
        "interpretation": {"status": "accepted", "medicine_count": 1,
                           "accepted_count": 1, "review_required_count": 0, "medicines": []},
        "prescription_plan": {"status": "resolved", "medicine_count": 1,
                               "resolved_count": 1, "review_required_count": 0, "medicines": []},
        "safety_analysis": {"safety_status": "no_structural_issues_detected",
                             "medicine_count": 1, "issue_count": 0, "high_severity_count": 0,
                             "medium_severity_count": 0, "low_severity_count": 0,
                             "medicines": [], "prescription_issues": []},
    }

    monkeypatch.setattr("backend.main.extract_text_from_image", lambda _: raw_text)
    monkeypatch.setattr("backend.main.process_prescription", lambda _: analysis)

    resp = client.post(
        "/prescriptions/upload",
        files={"file": ("rx.png", create_test_image(), "image/png")},
    )
    assert resp.status_code == 200
    return resp.json()["prescription_id"]


def test_pdf_report_allowed_on_professional_plan(api_client, monkeypatch):
    """Professional plan (pdf_reports_enabled=True) returns a PDF."""
    prescription_id = _upload_prescription_for_report(api_client, monkeypatch)

    resp = api_client.get(f"/prescriptions/{prescription_id}/report")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    assert resp.content.startswith(b"%PDF")


def test_pdf_report_blocked_on_free_plan(free_plan_client, monkeypatch):
    """Free plan (pdf_reports_enabled=False) returns HTTP 403."""
    prescription_id = _upload_prescription_for_report(free_plan_client, monkeypatch)

    resp = free_plan_client.get(f"/prescriptions/{prescription_id}/report")

    assert resp.status_code == 403
    assert "plan" in resp.json()["detail"].lower()


def test_pdf_report_entitlement_is_per_organization(tmp_path, monkeypatch):
    """
    Org A (free, PDF disabled) gets 403.
    Org B (professional, PDF enabled) gets 200.
    Both prescriptions exist in the same DB.
    """
    from types import SimpleNamespace
    from uuid import uuid4
    from datetime import datetime, timezone

    engine, SessionLocal = _make_engine_and_session()

    org_a_id = uuid4()
    org_b_id = uuid4()

    db = SessionLocal()
    try:
        db.add(OrganizationPlanDB(
            organization_id=org_a_id, plan_tier="free",
            monthly_prescription_limit=25, period_start=datetime.now(timezone.utc),
            period_prescription_count=0, review_workflow_enabled=True,
            pdf_reports_enabled=False,
        ))
        db.add(OrganizationPlanDB(
            organization_id=org_b_id, plan_tier="professional",
            monthly_prescription_limit=500, period_start=datetime.now(timezone.utc),
            period_prescription_count=0, review_workflow_enabled=True,
            pdf_reports_enabled=True,
        ))
        db.commit()
    finally:
        db.close()

    user_a = SimpleNamespace(id=uuid4(), name="Org A", email="a@example.com",
                              role="pharmacist", organization_id=org_a_id, is_active=True)
    user_b = SimpleNamespace(id=uuid4(), name="Org B", email="b@example.com",
                              role="pharmacist", organization_id=org_b_id, is_active=True)

    raw_text = "Amoxicillin 500mg once daily"
    analysis = {
        "medicines": [{"name": "Amoxicillin", "generic_name": "Amoxicillin",
                        "strength_value": 500.0, "strength_unit": "mg"}],
        "safety_flags": [],
        "analysis_metadata": {"needs_review": False, "prescription_plan_status": "resolved"},
        "interpretation": {"status": "accepted", "medicine_count": 1,
                           "accepted_count": 1, "review_required_count": 0, "medicines": []},
        "prescription_plan": {"status": "resolved", "medicine_count": 1,
                               "resolved_count": 1, "review_required_count": 0, "medicines": []},
        "safety_analysis": {"safety_status": "no_structural_issues_detected",
                             "medicine_count": 1, "issue_count": 0, "high_severity_count": 0,
                             "medium_severity_count": 0, "low_severity_count": 0,
                             "medicines": [], "prescription_issues": []},
    }
    monkeypatch.setattr("backend.main.extract_text_from_image", lambda _: raw_text)
    monkeypatch.setattr("backend.main.process_prescription", lambda _: analysis)
    monkeypatch.setattr("backend.main.UPLOAD_DIR", tmp_path)

    try:
        # --- Org A: upload then try report ---
        client_a = _build_client(tmp_path, monkeypatch, user_a, SessionLocal)
        resp = client_a.post(
            "/prescriptions/upload",
            files={"file": ("rx.png", create_test_image(), "image/png")},
        )
        assert resp.status_code == 200
        rx_id_a = resp.json()["prescription_id"]

        resp_a = client_a.get(f"/prescriptions/{rx_id_a}/report")
        assert resp_a.status_code == 403

        # --- Org B: upload then get report ---
        client_b = _build_client(tmp_path, monkeypatch, user_b, SessionLocal)
        resp = client_b.post(
            "/prescriptions/upload",
            files={"file": ("rx.png", create_test_image(), "image/png")},
        )
        assert resp.status_code == 200
        rx_id_b = resp.json()["prescription_id"]

        resp_b = client_b.get(f"/prescriptions/{rx_id_b}/report")
        assert resp_b.status_code == 200
        assert resp_b.content.startswith(b"%PDF")

    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()
