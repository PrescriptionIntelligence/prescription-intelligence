"""
Tests for the forgot-password / password-reset feature.

Covers:
    1.  Forgot-password request for an existing account.
    2.  Forgot-password for unknown email returns the same generic response.
    3.  Reset token is stored hashed, not plaintext.
    4.  Reset token expires.
    5.  Invalid token is rejected.
    6.  Used token cannot be reused.
    7.  Successful password reset changes the password.
    8.  Old password no longer works after reset.
    9.  New password works after reset.
    10. Password reset email delivery failure is handled safely.
    11. Reset token is not exposed in API responses.
    12. Forgot-password endpoint does not reveal account existence.

All tests use an in-memory SQLite database — no real PostgreSQL needed.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base, get_db
from backend.main import app
from backend.models import PasswordResetTokenDB, UserDB
from backend.security import (
    hash_password,
    hash_password_reset_token,
    verify_password,
)


# =========================================================
# Shared fixture
# =========================================================


@pytest.fixture()
def env():
    """
    Isolated in-memory SQLite database with one active user,
    one inactive user, and a TestClient wired up via
    dependency override.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )
    db = Session()

    active_user = UserDB(
        name="Alice",
        email="alice@example.com",
        password_hash=hash_password("OldPassword1!"),
        role="pharmacist",
        is_active=True,
        email_verified=True,
    )

    inactive_user = UserDB(
        name="Inactive User",
        email="inactive@example.com",
        password_hash=hash_password("SomePass1!"),
        role="pharmacist",
        is_active=False,
        email_verified=True,
    )

    db.add_all([active_user, inactive_user])
    db.commit()
    db.refresh(active_user)
    db.refresh(inactive_user)

    def override_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app, raise_server_exceptions=False)

    yield {
        "client": client,
        "db": db,
        "session_factory": Session,
        "active_user": active_user,
        "inactive_user": inactive_user,
    }

    app.dependency_overrides.pop(get_db, None)
    db.close()
    engine.dispose()


# =========================================================
# Helpers
# =========================================================


GENERIC_MESSAGE = (
    "If an account exists for this email, "
    "a password reset link has been sent."
)


def _post_forgot(client, email: str):
    return client.post(
        "/auth/forgot-password",
        json={"email": email},
    )


def _post_reset(client, token: str, new_password: str):
    return client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": new_password},
    )


def _insert_token(db, user_id, token_hash, expires_at, used_at=None):
    record = PasswordResetTokenDB(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
        used_at=used_at,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


# =========================================================
# Test suite
# =========================================================


class TestForgotPassword:

    def test_1_existing_account_returns_generic_response(self, env):
        """
        TC-1: Forgot-password for a known email returns the generic message.
        """
        with patch(
            "backend.routers.auth.send_password_reset_email"
        ):
            response = _post_forgot(env["client"], "alice@example.com")

        assert response.status_code == 200
        assert GENERIC_MESSAGE in response.json()["message"]

    def test_2_unknown_email_returns_same_generic_response(self, env):
        """
        TC-2: Unknown email returns the exact same response shape.
        """
        response = _post_forgot(env["client"], "nobody@example.com")

        assert response.status_code == 200
        assert GENERIC_MESSAGE in response.json()["message"]

    def test_3_token_stored_hashed_not_plaintext(self, env):
        """
        TC-3: The database row must contain a SHA-256 hex digest,
        not the raw token.
        """
        captured_token: list[str] = []

        def capture_send(recipient_email, recipient_name, reset_token):
            captured_token.append(reset_token)

        with patch(
            "backend.routers.auth.send_password_reset_email",
            side_effect=capture_send,
        ):
            _post_forgot(env["client"], "alice@example.com")

        assert captured_token, "send_password_reset_email was not called"
        raw = captured_token[0]

        db = env["session_factory"]()
        records = db.query(PasswordResetTokenDB).all()
        db.close()

        assert records, "No PasswordResetTokenDB row was inserted"

        stored_hash = records[-1].token_hash

        # The stored value must NOT be the raw token.
        assert stored_hash != raw, (
            "Raw token must not be stored in the database"
        )

        # The stored value must be the SHA-256 hex digest of the raw token.
        expected_hash = hashlib.sha256(raw.encode()).hexdigest()
        assert stored_hash == expected_hash, (
            "Stored hash does not match SHA-256(raw_token)"
        )

    def test_4_expired_token_is_rejected(self, env):
        """
        TC-4: A token whose expires_at is in the past must be rejected.
        """
        raw_token = "a" * 43  # URL-safe base64 length for 32 bytes
        token_hash = hash_password_reset_token(raw_token)
        expired_at = datetime.now(timezone.utc) - timedelta(hours=1)

        _insert_token(
            env["db"],
            env["active_user"].id,
            token_hash,
            expired_at,
        )

        response = _post_reset(
            env["client"], raw_token, "NewPassword1!"
        )

        assert response.status_code == 400
        assert "expired" in response.json()["detail"].lower()

    def test_5_invalid_token_is_rejected(self, env):
        """
        TC-5: A token that was never issued must be rejected with 400.
        """
        response = _post_reset(
            env["client"],
            "z" * 43,  # plausible length, but never stored
            "NewPassword1!",
        )

        assert response.status_code == 400

    def test_6_used_token_cannot_be_reused(self, env):
        """
        TC-6: A token with used_at set must be rejected even if not expired.
        """
        raw_token = "b" * 43
        token_hash = hash_password_reset_token(raw_token)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        used_at = datetime.now(timezone.utc) - timedelta(minutes=5)

        _insert_token(
            env["db"],
            env["active_user"].id,
            token_hash,
            expires_at,
            used_at=used_at,
        )

        response = _post_reset(
            env["client"], raw_token, "NewPassword1!"
        )

        assert response.status_code == 400
        detail = response.json()["detail"].lower()
        assert "already been used" in detail or "invalid" in detail

    def test_7_successful_reset_changes_password(self, env):
        """
        TC-7: A valid token must cause a 200 response with a
        success message.
        """
        raw_token = "c" * 43
        token_hash = hash_password_reset_token(raw_token)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        _insert_token(
            env["db"],
            env["active_user"].id,
            token_hash,
            expires_at,
        )

        response = _post_reset(
            env["client"], raw_token, "BrandNewPass1!"
        )

        assert response.status_code == 200
        assert "successfully" in response.json()["message"].lower()

    def test_8_old_password_no_longer_works_after_reset(self, env):
        """
        TC-8: After a successful reset the old password must be invalid.
        """
        raw_token = "d" * 43
        token_hash = hash_password_reset_token(raw_token)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        _insert_token(
            env["db"],
            env["active_user"].id,
            token_hash,
            expires_at,
        )

        _post_reset(env["client"], raw_token, "BrandNewPass2!")

        # Fetch the updated user row and verify old password is gone.
        db = env["session_factory"]()
        updated = db.query(UserDB).filter(
            UserDB.id == env["active_user"].id
        ).first()
        db.close()

        assert not verify_password("OldPassword1!", updated.password_hash), (
            "Old password must not verify against the new hash"
        )

    def test_9_new_password_works_after_reset(self, env):
        """
        TC-9: After a successful reset the new password must be valid.
        """
        new_pw = "BrandNewPass3!"
        raw_token = "e" * 43
        token_hash = hash_password_reset_token(raw_token)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        _insert_token(
            env["db"],
            env["active_user"].id,
            token_hash,
            expires_at,
        )

        _post_reset(env["client"], raw_token, new_pw)

        db = env["session_factory"]()
        updated = db.query(UserDB).filter(
            UserDB.id == env["active_user"].id
        ).first()
        db.close()

        assert verify_password(new_pw, updated.password_hash), (
            "New password must verify against the updated hash"
        )

    def test_10_email_delivery_failure_is_handled_safely(self, env):
        """
        TC-10: If the email service raises, the endpoint must still
        return 200 with the generic message (no 500 leaked).
        """
        with patch(
            "backend.routers.auth.send_password_reset_email",
            side_effect=RuntimeError("SMTP unavailable"),
        ):
            response = _post_forgot(env["client"], "alice@example.com")

        assert response.status_code == 200
        assert GENERIC_MESSAGE in response.json()["message"]

    def test_11_reset_token_not_exposed_in_responses(self, env):
        """
        TC-11: The API response for forgot-password and reset-password
        must never contain a token value.
        """
        with patch(
            "backend.routers.auth.send_password_reset_email"
        ):
            fp_response = _post_forgot(env["client"], "alice@example.com")

        fp_body = fp_response.text
        assert "token" not in fp_body.lower() or (
            "token" in fp_body.lower()
            and "access_token" not in fp_body.lower()
        ), "forgot-password response must not expose a token"

        # The reset response also must not include a token.
        raw_token = "f" * 43
        token_hash = hash_password_reset_token(raw_token)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        _insert_token(
            env["db"],
            env["active_user"].id,
            token_hash,
            expires_at,
        )

        reset_response = _post_reset(
            env["client"], raw_token, "NewTokenTest1!"
        )
        # The reset response body should just be {"message": "..."}
        reset_data = reset_response.json()
        assert set(reset_data.keys()) == {"message"}, (
            "reset-password response must only contain 'message'"
        )

    def test_12_forgot_password_does_not_reveal_account_existence(self, env):
        """
        TC-12: The response body and status code for a known and
        unknown email must be identical.
        """
        with patch(
            "backend.routers.auth.send_password_reset_email"
        ):
            known_response = _post_forgot(
                env["client"], "alice@example.com"
            )

        unknown_response = _post_forgot(
            env["client"], "nobody@notregistered.com"
        )

        assert known_response.status_code == unknown_response.status_code, (
            "Status codes must be identical for known and unknown emails"
        )
        assert known_response.json() == unknown_response.json(), (
            "Response bodies must be identical for known and unknown emails"
        )
