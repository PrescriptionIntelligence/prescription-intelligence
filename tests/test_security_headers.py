"""
F-08 Regression tests — security headers middleware.

Verifies that every response from the API includes the required
security headers, and that HSTS is only added for HTTPS requests.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app


# =========================================================
# FIXTURE
# =========================================================


@pytest.fixture(scope="module")
def client():
    """TestClient with no DB dependency needed — tests only check headers."""
    # The /health endpoint doesn't require auth and is always available
    # without a real DB (it will 503 but still return headers).
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# =========================================================
# F-08 TEST CASES
# =========================================================


class TestSecurityHeaders:

    def _get_any_response(self, client):
        """Return a response from the root endpoint (no auth required)."""
        return client.get("/")

    def test_x_content_type_options_is_nosniff(self, client):
        """X-Content-Type-Options: nosniff must be present on every response."""
        res = self._get_any_response(client)
        assert "x-content-type-options" in res.headers, (
            "X-Content-Type-Options header missing"
        )
        assert res.headers["x-content-type-options"] == "nosniff"

    def test_x_frame_options_is_deny(self, client):
        """X-Frame-Options: DENY must be present on every response."""
        res = self._get_any_response(client)
        assert "x-frame-options" in res.headers, (
            "X-Frame-Options header missing"
        )
        assert res.headers["x-frame-options"] == "DENY"

    def test_referrer_policy_is_strict_origin(self, client):
        """Referrer-Policy: strict-origin-when-cross-origin must be set."""
        res = self._get_any_response(client)
        assert "referrer-policy" in res.headers, (
            "Referrer-Policy header missing"
        )
        assert res.headers["referrer-policy"] == "strict-origin-when-cross-origin"

    def test_hsts_absent_for_plain_http(self, client):
        """
        Strict-Transport-Security must NOT be set for plain HTTP requests.
        Enabling HSTS over HTTP would break local development by permanently
        redirecting browsers to HTTPS.
        """
        # TestClient uses http:// by default and sends no X-Forwarded-Proto
        res = self._get_any_response(client)
        assert "strict-transport-security" not in res.headers, (
            "HSTS must not be set for plain HTTP requests"
        )

    def test_hsts_present_when_forwarded_proto_is_https(self, client):
        """
        When a reverse proxy signals HTTPS via X-Forwarded-Proto,
        the response must include HSTS.
        """
        res = client.get("/", headers={"X-Forwarded-Proto": "https"})
        assert "strict-transport-security" in res.headers, (
            "HSTS must be set when X-Forwarded-Proto: https"
        )
        hsts = res.headers["strict-transport-security"]
        assert "max-age=31536000" in hsts
        assert "includeSubDomains" in hsts

    def test_hsts_absent_when_forwarded_proto_is_http(self, client):
        """
        X-Forwarded-Proto: http (plain proxy) must not trigger HSTS.
        """
        res = client.get("/", headers={"X-Forwarded-Proto": "http"})
        assert "strict-transport-security" not in res.headers, (
            "HSTS must not be set when X-Forwarded-Proto: http"
        )

    def test_security_headers_present_on_api_endpoints(self, client):
        """
        Security headers must appear on API responses, not just the root.
        """
        res = client.get("/health")
        assert res.headers.get("x-content-type-options") == "nosniff"
        assert res.headers.get("x-frame-options") == "DENY"
        assert res.headers.get("referrer-policy") == "strict-origin-when-cross-origin"

    def test_security_headers_present_on_404_responses(self, client):
        """
        Security headers must be present even on error responses.
        """
        res = client.get("/nonexistent-endpoint-xyz")
        assert res.headers.get("x-content-type-options") == "nosniff"
        assert res.headers.get("x-frame-options") == "DENY"

    def test_security_headers_present_on_post_with_validation_error(self, client):
        """
        Security headers must appear on POST responses, including Pydantic
        422 validation errors that never touch the database.
        """
        # Empty payload → missing required fields (name, email, password,
        # pharmacy_name) → FastAPI returns 422 Unprocessable Entity purely
        # from Pydantic validation, before any DB interaction.
        res = client.post(
            "/auth/register",
            json={},
        )
        assert res.status_code == 422
        assert res.headers["X-Content-Type-Options"] == "nosniff"
        assert res.headers["X-Frame-Options"] == "DENY"
        assert res.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
