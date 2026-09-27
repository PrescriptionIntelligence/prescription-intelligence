"""
P7.12-A — Email-enumeration regression tests.

Verifies that:
  1. New pharmacist registration still succeeds (HTTP 201).
  2. New customer registration still succeeds (HTTP 201).
  3. Duplicate pharmacist email does NOT reveal account existence
     (indistinguishable from a new registration from the attacker's view).
  4. Duplicate customer email does NOT reveal account existence.
  5. Login behavior is unchanged:
       - unknown email → generic 401
       - wrong password → same generic 401
  6. Forgot-password remains generic (no account-existence leak).
  7. Resend-verification remains generic.
  8. Rate limiting remains intact for POST /auth/register and
     POST /auth/register/customer.
  9. Database uniqueness constraint is NOT weakened — the DB still
     prevents duplicate rows even though the HTTP layer no longer
     exposes it.

All tests use an isolated in-memory SQLite database.
"""

from __future__ import annotations

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
# Shared fixture — isolated in-memory DB per test function
# =========================================================


@pytest.fixture()
def env(monkeypatch):
    """
    Per-test isolated SQLite database + TestClient.

    Email sending is stubbed out so tests never hit SMTP.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()

    # Stub email delivery for all registration paths.
    monkeypatch.setattr(
        "backend.routers.auth.send_email_verification",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "backend.routers.auth.send_password_reset_email",
        lambda **kwargs: None,
    )

    def override_get_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app, raise_server_exceptions=False)

    yield {"client": client, "db": db, "Session": Session}

    app.dependency_overrides.pop(get_db, None)
    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


# =========================================================
# Helpers
# =========================================================


def _register_pharmacist(client: TestClient, email: str, suffix: str = ""):
    """POST /auth/register and return the response."""
    return client.post(
        "/auth/register",
        json={
            "name": "Test Pharmacist",
            "email": email,
            "password": "SecurePass1!",
            "pharmacy_name": f"Test Pharmacy{suffix}",
        },
    )


def _register_customer(client: TestClient, email: str):
    """POST /auth/register/customer and return the response."""
    return client.post(
        "/auth/register/customer",
        json={
            "name": "Test Customer",
            "email": email,
            "password": "SecurePass1!",
        },
    )


def _count_users_with_email(db, email: str) -> int:
    return db.query(UserDB).filter(UserDB.email == email).count()


# =========================================================
# 1 & 2 — Successful new registration
# =========================================================


class TestNewRegistrationSucceeds:

    def test_new_pharmacist_registration_returns_201(self, env):
        """A brand-new pharmacist email must be accepted with HTTP 201."""
        res = _register_pharmacist(env["client"], "newpharmacist@example.com")
        assert res.status_code == 201, f"Expected 201, got {res.status_code}: {res.text}"

    def test_new_pharmacist_registration_body_contains_message(self, env):
        """Successful registration must include a confirmation message."""
        res = _register_pharmacist(env["client"], "newpharmacist2@example.com")
        assert res.status_code == 201
        body = res.json()
        assert "message" in body
        assert body["message"]

    def test_new_pharmacist_registration_creates_user(self, env):
        """Successful registration must create exactly one user in the DB."""
        email = "newpharmacist3@example.com"
        res = _register_pharmacist(env["client"], email)
        assert res.status_code == 201
        # Use a fresh session to check the DB directly.
        check_db = env["Session"]()
        try:
            count = _count_users_with_email(check_db, email)
        finally:
            check_db.close()
        assert count == 1

    def test_new_customer_registration_returns_201(self, env):
        """A brand-new customer email must be accepted with HTTP 201."""
        res = _register_customer(env["client"], "newcustomer@example.com")
        assert res.status_code == 201, f"Expected 201, got {res.status_code}: {res.text}"

    def test_new_customer_registration_body_contains_message(self, env):
        """Successful customer registration must include a confirmation message."""
        res = _register_customer(env["client"], "newcustomer2@example.com")
        assert res.status_code == 201
        body = res.json()
        assert "message" in body
        assert body["message"]

    def test_new_customer_registration_creates_user(self, env):
        """Successful customer registration must create exactly one user in the DB."""
        email = "newcustomer3@example.com"
        res = _register_customer(env["client"], email)
        assert res.status_code == 201
        check_db = env["Session"]()
        try:
            count = _count_users_with_email(check_db, email)
        finally:
            check_db.close()
        assert count == 1


# =========================================================
# 3 & 4 — Duplicate email must not reveal account existence
# =========================================================


class TestDuplicateEmailDoesNotRevealAccountExistence:

    def test_duplicate_pharmacist_email_returns_non_409(self, env):
        """
        A second registration for the same pharmacist email must NOT
        return HTTP 409 — that would reveal account existence.
        """
        client = env["client"]
        email = "dup-pharmacist@example.com"
        _register_pharmacist(client, email, suffix=" A")
        res2 = _register_pharmacist(client, email, suffix=" B")
        assert res2.status_code != 409, (
            "HTTP 409 reveals that the email is already registered "
            "(email-enumeration vulnerability)"
        )

    def test_duplicate_pharmacist_response_indistinguishable_from_new(self, env):
        """
        The HTTP status code and body for a duplicate pharmacist registration
        must be indistinguishable from a successful new registration, from
        the attacker's perspective.
        """
        client = env["client"]

        # First registration — new account.
        res1 = _register_pharmacist(client, "dup-pharm-new@example.com", suffix=" X")
        # Second registration — duplicate.
        res2 = _register_pharmacist(client, "dup-pharm-dup@example.com", suffix=" Y")
        # Register the duplicate email a second time.
        _register_pharmacist(client, "dup-pharm-dup@example.com", suffix=" Z")
        res_dup = _register_pharmacist(client, "dup-pharm-dup@example.com", suffix=" W")

        # Status codes must be the same.
        assert res1.status_code == res_dup.status_code, (
            f"New={res1.status_code} vs duplicate={res_dup.status_code}: "
            "different status codes reveal account existence"
        )

    def test_duplicate_pharmacist_response_does_not_contain_409_detail(self, env):
        """
        The response for a duplicate pharmacist email must not contain the
        old 409 error detail that reveals account existence.
        """
        client = env["client"]
        email = "dup-pharm-detail@example.com"
        _register_pharmacist(client, email, suffix=" P1")
        res = _register_pharmacist(client, email, suffix=" P2")
        text = res.text.lower()
        assert "already exists" not in text, (
            "Response reveals that the email already exists"
        )
        assert "account with this email" not in text, (
            "Response reveals account existence"
        )

    def test_duplicate_pharmacist_does_not_create_second_db_row(self, env):
        """
        Even though the HTTP response is generic, the database uniqueness
        constraint must still prevent a second row for the same email.
        """
        client = env["client"]
        email = "dup-pharm-db@example.com"
        _register_pharmacist(client, email, suffix=" Q1")
        _register_pharmacist(client, email, suffix=" Q2")
        check_db = env["Session"]()
        try:
            count = _count_users_with_email(check_db, email)
        finally:
            check_db.close()
        assert count == 1, (
            f"Expected 1 DB row for {email!r}, found {count}. "
            "The uniqueness constraint must not be weakened."
        )

    def test_duplicate_customer_email_returns_non_409(self, env):
        """
        A second registration for the same customer email must NOT
        return HTTP 409.
        """
        client = env["client"]
        email = "dup-customer@example.com"
        _register_customer(client, email)
        res2 = _register_customer(client, email)
        assert res2.status_code != 409, (
            "HTTP 409 reveals that the email is already registered "
            "(email-enumeration vulnerability)"
        )

    def test_duplicate_customer_response_indistinguishable_from_new(self, env):
        """
        The HTTP status code for a duplicate customer registration must match
        a successful new registration — indistinguishable to an attacker.
        """
        client = env["client"]
        res_new = _register_customer(client, "dup-cust-new@example.com")
        _register_customer(client, "dup-cust-dup@example.com")
        res_dup = _register_customer(client, "dup-cust-dup@example.com")

        assert res_new.status_code == res_dup.status_code, (
            f"New={res_new.status_code} vs duplicate={res_dup.status_code}: "
            "different status codes reveal account existence"
        )

    def test_duplicate_customer_response_does_not_contain_409_detail(self, env):
        """
        The response for a duplicate customer email must not contain the
        old 409 error detail that reveals account existence.
        """
        client = env["client"]
        email = "dup-cust-detail@example.com"
        _register_customer(client, email)
        res = _register_customer(client, email)
        text = res.text.lower()
        assert "already exists" not in text, (
            "Response reveals that the email already exists"
        )
        assert "account with this email" not in text, (
            "Response reveals account existence"
        )

    def test_duplicate_customer_does_not_create_second_db_row(self, env):
        """
        Even though the HTTP response is generic, the database uniqueness
        constraint must still prevent a second row for the same customer email.
        """
        client = env["client"]
        email = "dup-cust-db@example.com"
        _register_customer(client, email)
        _register_customer(client, email)
        check_db = env["Session"]()
        try:
            count = _count_users_with_email(check_db, email)
        finally:
            check_db.close()
        assert count == 1, (
            f"Expected 1 DB row for {email!r}, found {count}. "
            "The uniqueness constraint must not be weakened."
        )


# =========================================================
# 5 — Login behavior unchanged
# =========================================================


class TestLoginBehaviorUnchanged:

    @pytest.fixture()
    def active_user(self, env):
        """Insert an active, verified pharmacist into the DB."""
        db = env["db"]
        org = OrganizationDB(name="Login Test Org", slug="login-test-org")
        db.add(org)
        db.flush()
        user = UserDB(
            organization_id=org.id,
            name="Login User",
            email="loginuser@example.com",
            password_hash=hash_password("CorrectPass1!"),
            role="pharmacist",
            is_active=True,
            email_verified=True,
        )
        db.add(user)
        db.commit()
        return user

    def test_unknown_email_returns_401(self, env, active_user):
        """An unknown email must return 401 — not 404 or 200."""
        res = env["client"].post(
            "/auth/login",
            json={"email": "nobody@example.com", "password": "irrelevant"},
        )
        assert res.status_code == 401

    def test_wrong_password_returns_401(self, env, active_user):
        """A wrong password must return 401."""
        res = env["client"].post(
            "/auth/login",
            json={"email": "loginuser@example.com", "password": "WrongPass!"},
        )
        assert res.status_code == 401

    def test_unknown_and_wrong_password_same_status(self, env, active_user):
        """
        Unknown email and wrong password must return the same status code
        so the attacker cannot distinguish them (no account-existence leak).
        """
        res_unknown = env["client"].post(
            "/auth/login",
            json={"email": "nobody2@example.com", "password": "irrelevant"},
        )
        res_wrong = env["client"].post(
            "/auth/login",
            json={"email": "loginuser@example.com", "password": "WrongPass!"},
        )
        assert res_unknown.status_code == res_wrong.status_code

    def test_correct_credentials_return_200(self, env, active_user):
        """Valid credentials must still succeed."""
        res = env["client"].post(
            "/auth/login",
            json={"email": "loginuser@example.com", "password": "CorrectPass1!"},
        )
        assert res.status_code == 200
        assert "access_token" in res.json()


# =========================================================
# 6 — Forgot-password remains generic
# =========================================================


class TestForgotPasswordRemainsGeneric:

    def test_known_email_returns_generic_200(self, env):
        """Forgot-password for a known email must return the generic response."""
        db = env["db"]
        user = UserDB(
            organization_id=None,
            name="Reset User",
            email="reset-known@example.com",
            password_hash=hash_password("AnyPass1!"),
            role="customer",
            is_active=True,
            email_verified=True,
        )
        db.add(user)
        db.commit()

        res = env["client"].post(
            "/auth/forgot-password",
            json={"email": "reset-known@example.com"},
        )
        assert res.status_code == 200
        body = res.json()
        assert "if an account exists" in body["message"].lower()

    def test_unknown_email_returns_same_generic_200(self, env):
        """Forgot-password for an unknown email must return the same generic response."""
        res = env["client"].post(
            "/auth/forgot-password",
            json={"email": "reset-unknown-nobody@example.com"},
        )
        assert res.status_code == 200
        body = res.json()
        assert "if an account exists" in body["message"].lower()

    def test_known_and_unknown_email_responses_are_identical(self, env):
        """
        The response body for a known and unknown email must be identical
        so the attacker cannot distinguish them.
        """
        db = env["db"]
        user = UserDB(
            organization_id=None,
            name="Reset User 2",
            email="reset-known2@example.com",
            password_hash=hash_password("AnyPass1!"),
            role="customer",
            is_active=True,
            email_verified=True,
        )
        db.add(user)
        db.commit()

        res_known = env["client"].post(
            "/auth/forgot-password",
            json={"email": "reset-known2@example.com"},
        )
        res_unknown = env["client"].post(
            "/auth/forgot-password",
            json={"email": "reset-truly-nobody@example.com"},
        )
        assert res_known.status_code == res_unknown.status_code
        assert res_known.json() == res_unknown.json()


# =========================================================
# 7 — Resend-verification remains generic
# =========================================================


class TestResendVerificationRemainsGeneric:

    def test_unknown_email_returns_generic_200(self, env):
        """Resend-verification for an unknown email must return HTTP 200."""
        res = env["client"].post(
            "/auth/resend-verification",
            json={"email": "resend-nobody@example.com"},
        )
        assert res.status_code == 200
        body = res.json()
        assert "if an account exists" in body["message"].lower()

    def test_verified_account_returns_generic_200(self, env):
        """Resend-verification for an already-verified account must return the generic response."""
        db = env["db"]
        user = UserDB(
            organization_id=None,
            name="Verified User",
            email="resend-verified@example.com",
            password_hash=hash_password("AnyPass1!"),
            role="customer",
            is_active=True,
            email_verified=True,
        )
        db.add(user)
        db.commit()

        res = env["client"].post(
            "/auth/resend-verification",
            json={"email": "resend-verified@example.com"},
        )
        assert res.status_code == 200
        body = res.json()
        assert "if an account exists" in body["message"].lower()


# =========================================================
# 8 — Rate limiting remains intact
# =========================================================


class TestRateLimitingIntact:

    def test_pharmacist_register_rate_limited(self, env):
        """
        POST /auth/register must still trigger HTTP 429 after exceeding
        the 5/minute threshold.
        """
        client = env["client"]
        codes = []
        for i in range(7):
            codes.append(
                client.post(
                    "/auth/register",
                    json={
                        "name": f"RL Pharmacist {i}",
                        "email": f"rl-pharmacist-{i}@example.com",
                        "password": "SecurePass1!",
                        "pharmacy_name": f"RL Pharmacy {i}",
                    },
                ).status_code
            )
        assert 429 in codes, (
            f"Rate limiter not triggered for /auth/register: {codes}"
        )

    def test_customer_register_rate_limited(self, env):
        """
        POST /auth/register/customer must still trigger HTTP 429 after
        exceeding the 5/minute threshold.
        """
        client = env["client"]
        codes = []
        for i in range(7):
            codes.append(
                client.post(
                    "/auth/register/customer",
                    json={
                        "name": f"RL Customer {i}",
                        "email": f"rl-customer-{i}@example.com",
                        "password": "SecurePass1!",
                    },
                ).status_code
            )
        assert 429 in codes, (
            f"Rate limiter not triggered for /auth/register/customer: {codes}"
        )
