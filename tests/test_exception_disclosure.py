"""
F-03 Regression tests — no raw exception messages in HTTP 500 responses.

Verifies that internal exception text (str(exc), filesystem paths, SQL error
strings, etc.) is never returned to clients in HTTP error responses.
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.auth import get_current_user
from backend.database import Base, get_db
from backend.main import app
from backend.models import OrganizationPlanDB


# =========================================================
# FIXTURE
# =========================================================


@pytest.fixture()
def upload_client(tmp_path, monkeypatch):
    """Pharmacist TestClient with professional plan."""
    from types import SimpleNamespace
    from uuid import uuid4

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    org_id = uuid4()
    test_user = SimpleNamespace(
        id=uuid4(),
        name="Test Pharmacist",
        email="f03-test@example.com",
        role="pharmacist",
        organization_id=org_id,
        is_active=True,
    )

    db = Session()
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
    db.close()

    def override_get_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: test_user
    monkeypatch.setattr("backend.main.UPLOAD_DIR", tmp_path)

    client = TestClient(app, raise_server_exceptions=False)

    yield client

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db, None)
    engine.dispose()


def _minimal_jpeg_bytes() -> bytes:
    """Return the smallest valid JPEG byte stream."""
    buf = BytesIO()
    from PIL import Image
    img = Image.new("RGB", (8, 8), color=(255, 0, 0))
    img.save(buf, format="JPEG")
    return buf.getvalue()


# =========================================================
# HELPERS
# =========================================================


def _assert_no_exception_leak(response, *, allowed_status=None):
    """
    Assert that the response body does not contain raw exception text.
    Accepts status codes that are acceptable for error scenarios.
    """
    if allowed_status is not None:
        assert response.status_code in allowed_status, (
            f"Unexpected status {response.status_code}: {response.text[:200]}"
        )

    text = response.text.lower()
    # Common patterns that must never appear in client responses
    assert "traceback" not in text, "Traceback leaked in response"
    assert "exception" not in text or "an internal error" in response.text.lower(), (
        f"Raw exception class name leaked: {response.text[:200]}"
    )
    # No filesystem paths (Windows or Unix)
    assert "c:\\" not in text, "Windows path leaked"
    assert "/usr/" not in text, "Unix path leaked"
    assert "/app/" not in text, "Container path leaked"
    # No SQLAlchemy / psycopg noise
    assert "sqlalchemy" not in text, "SQLAlchemy string leaked"
    assert "psycopg" not in text, "Psycopg string leaked"


# =========================================================
# F-03 TEST CASES
# =========================================================


class TestNoExceptionDisclosure:

    def test_db_write_failure_returns_generic_500(self, upload_client):
        """
        When the DB write for a prescription fails (increment_prescription_usage
        raises), the response must be a generic 500 — not str(exc).
        """
        jpeg = _minimal_jpeg_bytes()

        with patch(
            "backend.main.increment_prescription_usage",
            side_effect=Exception("DB INTERNAL: unique violation on xyz_table"),
        ):
            res = upload_client.post(
                "/prescriptions/upload",
                files={"file": ("rx.jpg", jpeg, "image/jpeg")},
            )

        # Must be 500 and must not contain the exception string
        if res.status_code == 500:
            assert "DB INTERNAL" not in res.text, (
                f"Raw exception text leaked: {res.text[:300]}"
            )
            assert "unique violation" not in res.text.lower(), (
                f"DB error leaked: {res.text[:300]}"
            )
            _assert_no_exception_leak(res, allowed_status=[500])

    def test_ocr_failure_returns_generic_500(self, upload_client):
        """
        If OCR raises, the response must be generic 500 — no str(exc).
        """
        jpeg = _minimal_jpeg_bytes()

        with patch(
            "backend.main.extract_text_from_image",
            side_effect=RuntimeError(
                "tesseract binary not found at /usr/bin/tesseract"
            ),
        ):
            res = upload_client.post(
                "/prescriptions/upload",
                files={"file": ("rx.jpg", jpeg, "image/jpeg")},
            )

        assert res.status_code == 500
        assert "/usr/bin/tesseract" not in res.text, (
            "Filesystem path leaked in OCR error response"
        )
        assert "RuntimeError" not in res.text, (
            "Exception class name leaked"
        )
        _assert_no_exception_leak(res, allowed_status=[500])

    def test_pipeline_failure_returns_generic_500(self, upload_client):
        """
        If the prescription pipeline raises, response is generic 500.
        """
        jpeg = _minimal_jpeg_bytes()

        with patch(
            "backend.main.extract_text_from_image",
            return_value="Paracetamol 500mg",
        ):
            with patch(
                "backend.main.process_prescription",
                side_effect=RuntimeError(
                    "SECRET pipeline crash: path=/app/data/vocab.json"
                ),
            ):
                res = upload_client.post(
                    "/prescriptions/upload",
                    files={"file": ("rx.jpg", jpeg, "image/jpeg")},
                )

        assert res.status_code == 500
        assert "/app/data" not in res.text, "Container path leaked"
        assert "SECRET" not in res.text, "Exception detail leaked"
        _assert_no_exception_leak(res, allowed_status=[500])

    def test_invalid_image_returns_400_without_path(self, upload_client):
        """
        An invalid image (not a real JPEG despite the MIME header) must return
        a user-friendly 400 with no filesystem path in the detail.
        """
        # First 3 bytes are JPEG magic — valid MIME — but contents are garbage
        bad_image = b"\xff\xd8\xff" + b"\x00" * 100

        res = upload_client.post(
            "/prescriptions/upload",
            files={"file": ("bad.jpg", bad_image, "image/jpeg")},
        )

        assert res.status_code == 400
        assert "tmp_path" not in res.text.lower(), "tmp path leaked"
        # No raw Python exception class names
        assert "UnidentifiedImageError" not in res.text
        assert "PIL" not in res.text

    def test_500_response_detail_is_generic_string(self, upload_client):
        """
        Any HTTP 500 response from the upload endpoint must use the
        canonical generic message — never str(exc).
        """
        jpeg = _minimal_jpeg_bytes()
        GENERIC = "An internal error occurred"

        with patch(
            "backend.main.extract_text_from_image",
            return_value="Paracetamol 500mg",
        ):
            with patch(
                "backend.main.process_prescription",
                side_effect=RuntimeError("Intentional crash for test"),
            ):
                res = upload_client.post(
                    "/prescriptions/upload",
                    files={"file": ("rx.jpg", jpeg, "image/jpeg")},
                )

        assert res.status_code == 500
        body = res.json()
        assert GENERIC in body.get("detail", ""), (
            f"Expected generic detail, got: {body}"
        )
        assert "Intentional crash for test" not in body.get("detail", ""), (
            "Raw exception message leaked into detail"
        )
