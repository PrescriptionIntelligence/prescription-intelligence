"""
F-04 Regression tests — magic-byte image validation on upload.

Verifies that the prescription upload endpoint inspects actual file bytes
(not just the client-supplied Content-Type) and rejects mismatched files
before writing anything to disk.
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

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


# =========================================================
# FIXTURES
# =========================================================


@pytest.fixture()
def upload_client(tmp_path, monkeypatch):
    """Pharmacist on professional plan with a tmp upload dir."""
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
        name="F04 Pharmacist",
        email="f04@example.com",
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

    yield TestClient(app, raise_server_exceptions=False)

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db, None)
    engine.dispose()


# =========================================================
# HELPERS
# =========================================================


def _real_jpeg() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (8, 8), color=(10, 20, 30)).save(buf, format="JPEG")
    return buf.getvalue()


def _real_png() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (8, 8), color=(10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


# =========================================================
# F-04 TEST CASES
# =========================================================


class TestMagicByteValidation:

    # ------ ACCEPT cases ------

    def test_real_jpeg_is_accepted(self, upload_client):
        """A genuine JPEG with matching Content-Type is accepted."""
        from unittest.mock import patch

        with patch("backend.main.extract_text_from_image", return_value=""):
            res = upload_client.post(
                "/prescriptions/upload",
                files={"file": ("rx.jpg", _real_jpeg(), "image/jpeg")},
            )
        # Not rejected by magic-byte check (200 or any non-400 magic-byte rejection)
        assert res.status_code != 400 or "image format" not in res.text.lower(), (
            f"Real JPEG was wrongly rejected: {res.text[:200]}"
        )

    def test_real_png_is_accepted(self, upload_client):
        """A genuine PNG with matching Content-Type is accepted."""
        from unittest.mock import patch

        with patch("backend.main.extract_text_from_image", return_value=""):
            res = upload_client.post(
                "/prescriptions/upload",
                files={"file": ("rx.png", _real_png(), "image/png")},
            )
        assert res.status_code != 400 or "image format" not in res.text.lower(), (
            f"Real PNG was wrongly rejected: {res.text[:200]}"
        )

    # ------ REJECT cases ------

    def test_plain_text_with_jpeg_content_type_is_rejected(self, upload_client):
        """
        A plain-text file claiming to be JPEG must be rejected.
        Content-Type alone is not trusted.
        """
        res = upload_client.post(
            "/prescriptions/upload",
            files={
                "file": (
                    "rx.jpg",
                    b"This is not a JPEG file at all.",
                    "image/jpeg",
                )
            },
        )
        assert res.status_code == 400
        body = res.json()
        assert "image format" in body.get("detail", "").lower(), (
            f"Unexpected detail: {body}"
        )

    def test_html_with_jpeg_content_type_is_rejected(self, upload_client):
        """
        HTML content claiming to be JPEG must be rejected before disk write.
        """
        html = b"<html><body>You have been pwned</body></html>"
        res = upload_client.post(
            "/prescriptions/upload",
            files={"file": ("rx.jpg", html, "image/jpeg")},
        )
        assert res.status_code == 400

    def test_pdf_with_jpeg_content_type_is_rejected(self, upload_client):
        """
        A PDF (starts with %PDF) claiming to be JPEG is rejected.
        """
        pdf_header = b"%PDF-1.4 fake content"
        res = upload_client.post(
            "/prescriptions/upload",
            files={"file": ("rx.jpg", pdf_header, "image/jpeg")},
        )
        assert res.status_code == 400

    def test_zero_bytes_with_jpeg_content_type_is_rejected(self, upload_client):
        """
        An empty file must be rejected (empty check fires before magic-byte check).
        """
        res = upload_client.post(
            "/prescriptions/upload",
            files={"file": ("rx.jpg", b"", "image/jpeg")},
        )
        assert res.status_code == 400

    def test_jpeg_magic_bytes_only_no_real_image_rejected_by_pillow(
        self, upload_client
    ):
        """
        A file with JPEG magic bytes but invalid image data passes the
        magic-byte check and is then caught by Pillow validation — still
        returning a 400 (not 500).
        """
        # Valid JPEG signature but corrupt body
        bad_jpeg = b"\xff\xd8\xff" + b"\x00" * 50

        res = upload_client.post(
            "/prescriptions/upload",
            files={"file": ("bad.jpg", bad_jpeg, "image/jpeg")},
        )
        # Magic-byte check passes (correct signature), Pillow will reject it
        assert res.status_code == 400
        # Still no internal path/exception leak
        assert "/app/" not in res.text
        assert "traceback" not in res.text.lower()

    def test_rejected_file_is_not_written_to_disk(self, upload_client, tmp_path):
        """
        Files rejected by magic-byte validation must not be written to disk.
        """
        res = upload_client.post(
            "/prescriptions/upload",
            files={
                "file": (
                    "malicious.jpg",
                    b"NOTAJPEG fake content here",
                    "image/jpeg",
                )
            },
        )
        assert res.status_code == 400
        # No files should have been written
        written = list(tmp_path.iterdir())
        assert written == [], (
            f"Files were written despite magic-byte rejection: {written}"
        )

    def test_png_bytes_with_jpeg_content_type_passes_magic_check(
        self, upload_client
    ):
        """
        A real PNG sent with Content-Type image/jpeg passes the MIME check
        (image/jpeg is allowed), passes the magic-byte check (PNG signature
        is valid), and is processed normally.  The server does not need to
        reject valid PNG content just because the MIME header says jpeg.
        """
        from unittest.mock import patch

        with patch("backend.main.extract_text_from_image", return_value=""):
            res = upload_client.post(
                "/prescriptions/upload",
                files={"file": ("rx.png", _real_png(), "image/jpeg")},
            )
        # Should not be rejected by magic-byte check (PNG signature is valid).
        assert res.status_code != 400 or "image format" not in res.text.lower(), (
            "Real PNG was wrongly rejected by magic-byte check"
        )
