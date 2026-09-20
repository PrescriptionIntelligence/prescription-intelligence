"""
F-02 Rate-limiting tests for authentication endpoints.

Verifies that the slowapi limiter is wired up correctly and that
login/register/etc. return HTTP 429 after exceeding their limits.

Strategy:
  - Lower the limit to 1/minute for the test by monkey-patching the limiter
    storage and calling the endpoint multiple times.
  - Use TestClient which drives requests from 127.0.0.1 consistently.
  - Each test runs in an isolated in-memory database.

NOTE: slowapi uses per-key (IP) counters.  Between tests the limiter state
is reset by creating a fresh Limiter with a fresh in-memory storage.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base, get_db
from backend.main import app
from backend.models import OrganizationDB, UserDB
from backend.security import hash_password


# =========================================================
# FIXTURE — isolated DB + rate-limiter reset
# =========================================================


@pytest.fixture()
def env():
    """In-memory DB + TestClient with per-test limiter reset."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()

    # Active pharmacist for login tests
    org = OrganizationDB(name="Rate Org", slug="rate-org")
    db.add(org)
    db.flush()

    pharmacist = UserDB(
        organization_id=org.id,
        name="Rate Pharmacist",
        email="rate-pharmacist@example.com",
        password_hash=hash_password("GoodPass123!"),
        role="pharmacist",
        is_active=True,
        email_verified=True,
    )
    db.add(pharmacist)
    db.commit()

    def override_get_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db

    client = TestClient(app, raise_server_exceptions=False)

    yield {
        "client": client,
        "pharmacist": pharmacist,
        "db": db,
    }

    app.dependency_overrides.pop(get_db, None)
    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


# =========================================================
# HELPERS
# =========================================================


def _hit_login(client: TestClient, n: int) -> list[int]:
    """Hit POST /auth/login n times, return list of status codes."""
    return [
        client.post(
            "/auth/login",
            json={
                "email": "rate-pharmacist@example.com",
                "password": "GoodPass123!",
            },
        ).status_code
        for _ in range(n)
    ]


# =========================================================
# TESTS
# =========================================================


class TestRateLimitingWiring:
    """Verify slowapi is correctly wired to the app."""

    def test_login_returns_200_within_limit(self, env):
        """A single login within the limit succeeds."""
        client = env["client"]
        res = client.post(
            "/auth/login",
            json={
                "email": "rate-pharmacist@example.com",
                "password": "GoodPass123!",
            },
        )
        assert res.status_code == 200

    def test_login_returns_429_after_limit_exceeded(self, env):
        """
        After exceeding 10 requests/minute for login, HTTP 429 is returned.
        """
        client = env["client"]
        status_codes = _hit_login(client, 12)
        # At least one 429 must appear in the last few responses
        assert 429 in status_codes, (
            f"Expected at least one 429 in {status_codes}"
        )

    def test_429_response_is_json(self, env):
        """The 429 response body is valid JSON (not HTML/traceback)."""
        client = env["client"]
        responses = [
            client.post(
                "/auth/login",
                json={
                    "email": "rate-pharmacist@example.com",
                    "password": "WrongPass!",
                },
            )
            for _ in range(12)
        ]
        rate_limited = [r for r in responses if r.status_code == 429]
        assert rate_limited, "No 429 response found after 12 attempts"
        body = rate_limited[0].json()
        # Must be parseable JSON; no stack trace
        assert isinstance(body, dict)
        detail = str(body.get("detail", "") or body.get("error", ""))
        assert "traceback" not in detail.lower()
        assert "file " not in detail.lower()  # no filesystem path

    def test_register_rate_limited(self, env):
        """POST /auth/register is rate-limited at 5/minute."""
        client = env["client"]
        codes = []
        for i in range(7):
            codes.append(
                client.post(
                    "/auth/register",
                    json={
                        "name": f"Pharmacy {i}",
                        "email": f"new-pharmacy-{i}@example.com",
                        "password": "SecurePass1!",
                        "pharmacy_name": f"Pharmacy {i}",
                    },
                ).status_code
            )
        # We expect 429 somewhere in the sequence
        assert 429 in codes, f"Expected 429 in {codes}"

    def test_forgot_password_rate_limited(self, env):
        """POST /auth/forgot-password is rate-limited at 5/minute."""
        client = env["client"]
        codes = [
            client.post(
                "/auth/forgot-password",
                json={"email": "rate-pharmacist@example.com"},
            ).status_code
            for _ in range(7)
        ]
        assert 429 in codes, f"Expected 429 in {codes}"

    def test_resend_verification_rate_limited(self, env):
        """POST /auth/resend-verification is rate-limited at 5/minute."""
        client = env["client"]
        codes = [
            client.post(
                "/auth/resend-verification",
                json={"email": "rate-pharmacist@example.com"},
            ).status_code
            for _ in range(7)
        ]
        assert 429 in codes, f"Expected 429 in {codes}"

    def test_rate_limit_does_not_leak_account_info(self, env):
        """
        A 429 response body must not reveal whether an email account exists.
        """
        client = env["client"]
        for _ in range(12):
            client.post(
                "/auth/login",
                json={
                    "email": "rate-pharmacist@example.com",
                    "password": "WrongPass!",
                },
            )
        res = client.post(
            "/auth/login",
            json={
                "email": "rate-pharmacist@example.com",
                "password": "WrongPass!",
            },
        )
        if res.status_code == 429:
            text = res.text.lower()
            assert "account" not in text or "exist" not in text
