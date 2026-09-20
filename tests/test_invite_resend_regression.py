"""
F-01 Regression tests — invited-pharmacist resend-verification guard.

Verifies that POST /auth/resend-verification never overwrites the invitation
token of an unactivated invited pharmacist, and that the original token
remains usable via POST /auth/accept-invite.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base, get_db
from backend.main import app
from backend.models import OrganizationDB, UserDB
from backend.security import (
    generate_email_verification_token,
    hash_email_verification_token,
    hash_password,
)


# =========================================================
# FIXTURES
# =========================================================


@pytest.fixture()
def env():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = Session()

    org = OrganizationDB(name="Invite Org", slug="invite-org-resend")
    db.add(org)
    db.flush()

    # Active pharmacist who can later log in (used to confirm
    # the active/verified fast-path is unaffected).
    active_pharmacist = UserDB(
        organization_id=org.id,
        name="Active Pharmacist",
        email="active-pharmacist-resend@example.com",
        password_hash=hash_password("pass123"),
        role="pharmacist",
        is_active=True,
        email_verified=True,
    )
    db.add(active_pharmacist)
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
        "db": db,
        "org": org,
        "Session": Session,
        "active_pharmacist": active_pharmacist,
    }

    app.dependency_overrides.pop(get_db, None)
    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _create_pending_invite(db, org_id: object, email: str = "invited@example.com"):
    """Create an unactivated invited pharmacist account and return (user, raw_token)."""
    raw_token = generate_email_verification_token()
    token_hash = hash_email_verification_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=72)
    placeholder = generate_email_verification_token()

    user = UserDB(
        organization_id=org_id,
        name="Invited Pharmacist",
        email=email,
        password_hash=hash_password(placeholder),
        role="pharmacist",
        email_verified=False,
        is_active=False,
        email_verification_token_hash=token_hash,
        email_verification_expires_at=expires_at,
    )
    db.add(user)
    db.commit()
    return user, raw_token


# =========================================================
# F-01 TEST CASES
# =========================================================


class TestInviteResendGuard:
    """resend-verification must not overwrite an invitation token."""

    def test_resend_for_invited_pharmacist_does_not_overwrite_token(self, env):
        """
        Calling resend-verification for an invited pharmacist returns the
        invitation-specific message and does NOT modify the token hash.
        """
        client = env["client"]
        db = env["db"]
        org = env["org"]

        user, raw_token = _create_pending_invite(
            db, org.id, "invited-no-overwrite@example.com"
        )
        original_hash = user.email_verification_token_hash

        res = client.post(
            "/auth/resend-verification",
            json={"email": user.email},
        )

        assert res.status_code == 200
        body = res.json()
        # Must mention invitation, not generic "verification email sent"
        assert "invitation" in body["message"].lower()

        # Token hash in DB must be unchanged
        db.refresh(user)
        assert user.email_verification_token_hash == original_hash

    def test_original_invite_token_still_usable_after_resend_call(self, env):
        """
        After calling resend-verification for an invited pharmacist (which
        should be a no-op), the original invite token must still work on
        POST /auth/accept-invite.
        """
        client = env["client"]
        db = env["db"]
        org = env["org"]

        user, raw_token = _create_pending_invite(
            db, org.id, "invited-token-usable@example.com"
        )

        # Call resend-verification (should be a no-op for this account)
        client.post(
            "/auth/resend-verification",
            json={"email": user.email},
        )

        # Original token must still activate the account
        res = client.post(
            "/auth/accept-invite",
            json={
                "email": user.email,
                "token": raw_token,
                "password": "SecurePass123!",
            },
        )

        assert res.status_code == 200, f"accept-invite failed: {res.json()}"

    def test_invited_account_remains_inactive_after_resend_call(self, env):
        """
        An invited account must stay is_active=False / email_verified=False
        after a resend-verification call.
        """
        client = env["client"]
        db = env["db"]
        org = env["org"]

        user, _ = _create_pending_invite(
            db, org.id, "invited-stays-inactive@example.com"
        )

        client.post(
            "/auth/resend-verification",
            json={"email": user.email},
        )

        db.refresh(user)
        assert user.is_active is False
        assert user.email_verified is False

    def test_resend_response_does_not_confirm_email_existence_for_unknown(self, env):
        """
        An unknown email must return the generic enumeration-safe response.
        """
        client = env["client"]

        res = client.post(
            "/auth/resend-verification",
            json={"email": "nonexistent-resend@example.com"},
        )

        assert res.status_code == 200
        body = res.json()
        # Generic message, not an invitation-specific one
        assert "invitation" not in body["message"].lower()
        assert "if an account exists" in body["message"].lower()

    def test_resend_for_active_verified_pharmacist_returns_generic(self, env):
        """
        An already-verified active pharmacist gets the generic response
        (previously returned a distinct 'already verified' message — now
        normalised to the generic response to prevent enumeration).
        """
        client = env["client"]
        active_pharmacist = env["active_pharmacist"]

        res = client.post(
            "/auth/resend-verification",
            json={"email": active_pharmacist.email},
        )

        assert res.status_code == 200
        # Must NOT say "already verified" (that was the old distinct message)
        body = res.json()
        assert "if an account exists" in body["message"].lower()

    def test_multiple_resend_calls_do_not_accumulate_token_changes_for_invite(
        self, env
    ):
        """
        Calling resend-verification multiple times for the same invited
        pharmacist must not change the stored token hash on any call.
        """
        client = env["client"]
        db = env["db"]
        org = env["org"]

        user, raw_token = _create_pending_invite(
            db, org.id, "invited-multi-resend@example.com"
        )
        original_hash = user.email_verification_token_hash

        for _ in range(3):
            client.post(
                "/auth/resend-verification",
                json={"email": user.email},
            )

        db.refresh(user)
        assert user.email_verification_token_hash == original_hash

    def test_invited_customer_account_not_affected_by_guard(self, env):
        """
        The invite guard targets pharmacists only.  A customer account that
        is inactive and unverified (unusual but possible) must still go
        through the normal resend flow (token is replaced, not blocked).
        """
        db = env["db"]
        client = env["client"]

        # Inactive, unverified customer (not invited via invite flow)
        raw_token = generate_email_verification_token()
        token_hash = hash_email_verification_token(raw_token)
        customer_user = UserDB(
            organization_id=None,
            name="Unverified Customer",
            email="unverified-customer-resend@example.com",
            password_hash=hash_password("pass"),
            role="customer",
            email_verified=False,
            is_active=True,  # customer accounts are active by default
            email_verification_token_hash=token_hash,
            email_verification_expires_at=(
                datetime.now(timezone.utc) + timedelta(minutes=30)
            ),
        )
        db.add(customer_user)
        db.commit()

        # Customer resend should go through the normal path (returns
        # generic response and replaces token), not the invite guard.
        res = client.post(
            "/auth/resend-verification",
            json={"email": customer_user.email},
        )

        # Generic response (email send will fail — SMTP not configured — so
        # we only check status is not blocked by the invite guard)
        assert res.status_code in (200, 503)
        body = res.json()
        # Must NOT show invitation message
        assert "invitation" not in body.get("message", "").lower()
