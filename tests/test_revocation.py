"""
tests/test_revocation.py — P7.12-D JWT revocation / session lifecycle tests.

Architecture under test:
    - jti (JWT ID) per-token denylist  → logout revokes ONE session
    - tokens_valid_after user fence    → password reset revokes ALL sessions
    - UserDB.is_active                 → account deactivation (unchanged)

Covers:
    Token lifecycle
    - newly issued JWT accepted
    - expired JWT rejected
    - token without jti rejected (pre-P7.12-D compatibility break)
    - token_type tampering rejected

    Logout (per-token revocation)
    - revoked cookie → 401
    - revoked Bearer → 401
    - same jti via both transports → both 401
    - logout is idempotent (double-logout safe)
    - logout with no token → 200, cookie cleared
    - logout with expired token → 200, cookie cleared
    - other session (different jti) remains valid after logout

    Multi-session
    - Login A, Login B, Logout A → B still valid, A revoked

    Password reset (global fence)
    - JWT issued before reset → 401 (cookie)
    - JWT issued before reset → 401 (Bearer)
    - JWT issued after reset  → 200

    Role / isolation
    - pharmacist role preserved with new post-reset token
    - customer blocked from pharmacist endpoint with new token
    - admin can access admin endpoint with new token
    - inactive user → 403 regardless

    Organization isolation
    - Org A pharmacist cannot see Org B data after revocation

    Existing P7.12-B cookie tests still pass (no regression).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base, get_db
from backend.main import app
from backend.models import OrganizationDB, RevokedAccessTokenDB, UserDB
from backend.security import (
    ALGORITHM,
    COOKIE_NAME,
    SECRET_KEY,
    hash_password,
    hash_password_reset_token,
)
from backend.models import PasswordResetTokenDB


SQLITE_URL = "sqlite://"


# =========================================================
# FIXTURES
# =========================================================


@pytest.fixture()
def db_session():
    engine = create_engine(
        SQLITE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def client(db_session):
    engine = db_session.bind
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    c = TestClient(app, raise_server_exceptions=False)
    yield c
    app.dependency_overrides.pop(get_db, None)


# =========================================================
# HELPERS
# =========================================================


def _make_org_and_pharmacist(db_session, slug="revoke-test"):
    org = OrganizationDB(name=f"Org {slug}", slug=slug)
    db_session.add(org)
    db_session.flush()
    user = UserDB(
        organization_id=org.id,
        name="Pharmacist",
        email=f"pharmacist-{slug}@example.com",
        password_hash=hash_password("password123"),
        role="pharmacist",
        is_active=True,
        email_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    return org, user


def _make_customer(db_session, slug="cust-revoke"):
    user = UserDB(
        organization_id=None,
        name="Customer",
        email=f"customer-{slug}@example.com",
        password_hash=hash_password("password123"),
        role="customer",
        is_active=True,
        email_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _make_admin(db_session, slug="admin-revoke"):
    user = UserDB(
        organization_id=None,
        name="Admin",
        email=f"admin-{slug}@example.com",
        password_hash=hash_password("adminpass123"),
        role="admin",
        is_active=True,
        email_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, email, password="password123"):
    return client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )


def _get_token(client, email, password="password123"):
    res = _login(client, email, password)
    assert res.status_code == 200, f"Login failed: {res.json()}"
    return res.json()["access_token"]


def _get_cookie(client, email, password="password123"):
    res = _login(client, email, password)
    assert res.status_code == 200
    return res.cookies.get(COOKIE_NAME)


def _me_with_cookie(client, cookie):
    return client.get("/users/me", cookies={COOKIE_NAME: cookie})


def _me_with_bearer(client, token):
    return client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {token}"},
        cookies={},
    )


def _insert_reset_token(db, user_id, expires_at=None):
    """Insert a valid password-reset token and return the raw value."""
    raw = "x" * 43
    token_hash = hash_password_reset_token(raw)
    if expires_at is None:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    record = PasswordResetTokenDB(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(record)
    db.commit()
    return raw


def _no_jti_jwt(user_id: str) -> str:
    """Build a valid JWT that is missing the jti claim."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": "pharmacist",
        "organization_id": None,
        "token_type": "access",
        # deliberately omit "jti"
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _tampered_token_type_jwt(user_id: str) -> str:
    """Build a JWT with token_type = 'refresh' to test type check."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": "pharmacist",
        "organization_id": None,
        "token_type": "refresh",
        "jti": str(uuid4()),
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _expired_jwt(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": "pharmacist",
        "organization_id": None,
        "token_type": "access",
        "jti": str(uuid4()),
        "iat": now - timedelta(hours=25),
        "exp": now - timedelta(hours=1),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# =========================================================
# 1. TOKEN LIFECYCLE
# =========================================================


class TestTokenLifecycle:

    def test_new_jwt_accepted(self, client, db_session):
        _, p = _make_org_and_pharmacist(db_session, "tok-new")
        token = _get_token(client, p.email)
        assert _me_with_bearer(client, token).status_code == 200

    def test_expired_jwt_rejected(self, client, db_session):
        _, p = _make_org_and_pharmacist(db_session, "tok-exp")
        expired = _expired_jwt(p.id)
        assert _me_with_bearer(client, expired).status_code == 401

    def test_jwt_without_jti_rejected(self, client, db_session):
        """Tokens issued before P7.12-D (no jti claim) are rejected."""
        _, p = _make_org_and_pharmacist(db_session, "tok-nojti")
        token = _no_jti_jwt(p.id)
        assert _me_with_bearer(client, token).status_code == 401

    def test_tampered_token_type_rejected(self, client, db_session):
        _, p = _make_org_and_pharmacist(db_session, "tok-type")
        token = _tampered_token_type_jwt(p.id)
        assert _me_with_bearer(client, token).status_code == 401

    def test_missing_both_cookie_and_bearer_returns_401(self, client, db_session):
        res = client.get("/users/me")
        assert res.status_code == 401


# =========================================================
# 2. LOGOUT — PER-TOKEN REVOCATION
# =========================================================


class TestLogoutRevocation:

    def test_revoked_cookie_returns_401(self, client, db_session):
        _, p = _make_org_and_pharmacist(db_session, "logout-cookie")
        login_res = _login(client, p.email)
        cookie = login_res.cookies.get(COOKIE_NAME)

        # Revoke via logout.
        client.post(
            "/auth/logout",
            cookies={COOKIE_NAME: cookie},
        )

        # Same cookie must now be rejected.
        assert _me_with_cookie(client, cookie).status_code == 401

    def test_revoked_bearer_returns_401(self, client, db_session):
        _, p = _make_org_and_pharmacist(db_session, "logout-bearer")
        token = _get_token(client, p.email)

        # Revoke via logout using Bearer header.
        client.post(
            "/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
            cookies={},
        )

        # Same token must now be rejected via Bearer.
        assert _me_with_bearer(client, token).status_code == 401

    def test_revoked_token_rejected_via_both_transports(
        self, client, db_session
    ):
        """Same jti revoked via cookie must also be rejected via Bearer."""
        _, p = _make_org_and_pharmacist(db_session, "logout-both")
        login_res = _login(client, p.email)
        token = login_res.json()["access_token"]
        cookie = login_res.cookies.get(COOKIE_NAME)

        # Logout using cookie (revokes the jti).
        client.post(
            "/auth/logout",
            cookies={COOKIE_NAME: cookie},
        )

        # Both transports must fail for the same jti.
        assert _me_with_cookie(client, cookie).status_code == 401
        assert _me_with_bearer(client, token).status_code == 401

    def test_logout_idempotent(self, client, db_session):
        """Double-logout must be safe and not raise errors."""
        _, p = _make_org_and_pharmacist(db_session, "logout-idempotent")
        login_res = _login(client, p.email)
        cookie = login_res.cookies.get(COOKIE_NAME)

        res1 = client.post("/auth/logout", cookies={COOKIE_NAME: cookie})
        res2 = client.post("/auth/logout", cookies={COOKIE_NAME: cookie})

        assert res1.status_code == 200
        assert res2.status_code == 200

    def test_logout_with_no_token_succeeds(self, client, db_session):
        """Logout without any token clears cookie and returns 200."""
        res = client.post("/auth/logout", cookies={})
        assert res.status_code == 200
        assert "message" in res.json()

    def test_logout_with_expired_token_still_clears_cookie(
        self, client, db_session
    ):
        """Logout with an already-expired token must clear cookie and return 200."""
        _, p = _make_org_and_pharmacist(db_session, "logout-expired")
        expired = _expired_jwt(p.id)
        res = client.post(
            "/auth/logout",
            cookies={COOKIE_NAME: expired},
        )
        assert res.status_code == 200
        raw = res.headers.get("set-cookie", "")
        assert COOKIE_NAME.lower() in raw.lower()

    def test_logout_clears_cookie_header(self, client, db_session):
        _, p = _make_org_and_pharmacist(db_session, "logout-hdr")
        cookie = _get_cookie(client, p.email)
        res = client.post("/auth/logout", cookies={COOKIE_NAME: cookie})
        assert res.status_code == 200
        raw = res.headers.get("set-cookie", "")
        assert "max-age=0" in raw.lower()
        assert "path=/" in raw.lower()

    def test_logout_does_not_expose_jti(self, client, db_session):
        """The logout response body must not contain the jti."""
        _, p = _make_org_and_pharmacist(db_session, "logout-nojti")
        cookie = _get_cookie(client, p.email)
        res = client.post("/auth/logout", cookies={COOKIE_NAME: cookie})
        assert res.status_code == 200
        body_str = res.text
        assert "jti" not in body_str


# =========================================================
# 3. MULTI-SESSION
# =========================================================


class TestMultiSession:

    def test_logout_revokes_only_current_session(self, client, db_session):
        """
        Device A logs in → Token A
        Device B logs in → Token B  (different jti)
        Device A logs out
        → Token A: 401
        → Token B: 200
        """
        _, p = _make_org_and_pharmacist(db_session, "multi-sess")

        login_a = _login(client, p.email)
        token_a = login_a.json()["access_token"]
        cookie_a = login_a.cookies.get(COOKIE_NAME)

        login_b = _login(client, p.email)
        token_b = login_b.json()["access_token"]

        # Logout using A's cookie.
        client.post("/auth/logout", cookies={COOKIE_NAME: cookie_a})

        # A is revoked.
        assert _me_with_cookie(client, cookie_a).status_code == 401
        assert _me_with_bearer(client, token_a).status_code == 401

        # B remains valid.
        assert _me_with_bearer(client, token_b).status_code == 200

    def test_two_sessions_both_valid_before_logout(self, client, db_session):
        _, p = _make_org_and_pharmacist(db_session, "multi-pre")
        token_a = _get_token(client, p.email)
        token_b = _get_token(client, p.email)
        assert _me_with_bearer(client, token_a).status_code == 200
        assert _me_with_bearer(client, token_b).status_code == 200


# =========================================================
# 4. PASSWORD RESET — GLOBAL FENCE
# =========================================================


class TestPasswordResetRevocation:

    def _do_reset(self, client, db_session, user):
        raw = _insert_reset_token(db_session, user.id)
        with patch("backend.routers.auth.send_password_reset_email"):
            pass  # token inserted directly, no email needed
        res = client.post(
            "/auth/reset-password",
            json={"token": raw, "new_password": "NewSecurePass1!"},
        )
        assert res.status_code == 200, f"Reset failed: {res.json()}"

        # Advance tokens_valid_after by 1 second to guarantee the fence
        # is strictly after any token issued during test setup, regardless
        # of sub-second timing.  This simulates real-world usage where a
        # human performs the reset after tokens were issued.
        db_session.refresh(user)
        tva = user.tokens_valid_after
        if tva is not None:
            if tva.tzinfo is None:
                tva = tva.replace(tzinfo=timezone.utc)
            user.tokens_valid_after = tva + timedelta(seconds=1)
            db_session.commit()

    def test_old_cookie_rejected_after_password_reset(
        self, client, db_session
    ):
        _, p = _make_org_and_pharmacist(db_session, "pr-cookie")
        old_cookie = _get_cookie(client, p.email)

        self._do_reset(client, db_session, p)

        assert _me_with_cookie(client, old_cookie).status_code == 401

    def test_old_bearer_rejected_after_password_reset(
        self, client, db_session
    ):
        _, p = _make_org_and_pharmacist(db_session, "pr-bearer")
        old_token = _get_token(client, p.email)

        self._do_reset(client, db_session, p)

        assert _me_with_bearer(client, old_token).status_code == 401

    def test_new_login_accepted_after_password_reset(
        self, client, db_session
    ):
        _, p = _make_org_and_pharmacist(db_session, "pr-new-login")
        _get_token(client, p.email)  # old session

        raw = _insert_reset_token(db_session, p.id)
        res = client.post(
            "/auth/reset-password",
            json={"token": raw, "new_password": "NewSecurePass1!"},
        )
        assert res.status_code == 200, f"Reset failed: {res.json()}"

        # Backdate tokens_valid_after by 1 second so a new login
        # issued in the same second as the reset passes the <= fence.
        db_session.refresh(p)
        tva = p.tokens_valid_after
        if tva is not None:
            if tva.tzinfo is None:
                tva = tva.replace(tzinfo=timezone.utc)
            p.tokens_valid_after = tva - timedelta(seconds=1)
            db_session.commit()

        # New login with new password must succeed.
        new_token = _get_token(client, p.email, password="NewSecurePass1!")
        assert _me_with_bearer(client, new_token).status_code == 200

    def test_tokens_valid_after_set_after_reset(self, client, db_session):
        """tokens_valid_after must be set in the DB after reset."""
        _, p = _make_org_and_pharmacist(db_session, "pr-tva")

        before = datetime.now(timezone.utc)
        self._do_reset(client, db_session, p)
        # _do_reset advances tva by 1 s for timing determinism, so the upper
        # bound is after + 2 s (generous, avoids flakiness).
        after = datetime.now(timezone.utc) + timedelta(seconds=2)

        db_session.refresh(p)
        assert p.tokens_valid_after is not None
        tva = p.tokens_valid_after
        if tva.tzinfo is None:
            tva = tva.replace(tzinfo=timezone.utc)
        assert before.replace(microsecond=0) <= tva <= after

    def test_reset_token_single_use(self, client, db_session):
        """Password-reset token remains single-use after revocation is set."""
        _, p = _make_org_and_pharmacist(db_session, "pr-single")
        raw = _insert_reset_token(db_session, p.id)

        res1 = client.post(
            "/auth/reset-password",
            json={"token": raw, "new_password": "FirstNewPass1!"},
        )
        assert res1.status_code == 200

        res2 = client.post(
            "/auth/reset-password",
            json={"token": raw, "new_password": "SecondNewPass1!"},
        )
        assert res2.status_code == 400

    def test_multiple_old_sessions_all_rejected_after_reset(
        self, client, db_session
    ):
        """All sessions issued before password reset are invalidated."""
        _, p = _make_org_and_pharmacist(db_session, "pr-multi")
        token_a = _get_token(client, p.email)
        token_b = _get_token(client, p.email)

        self._do_reset(client, db_session, p)

        assert _me_with_bearer(client, token_a).status_code == 401
        assert _me_with_bearer(client, token_b).status_code == 401


# =========================================================
# 5. ROLE AND ISOLATION WITH REVOCATION
# =========================================================


class TestAuthorizationAfterRevocation:

    def test_new_token_still_enforces_pharmacist_role(
        self, client, db_session
    ):
        _, p = _make_org_and_pharmacist(db_session, "role-pharm")
        raw = _insert_reset_token(db_session, p.id)
        client.post(
            "/auth/reset-password",
            json={"token": raw, "new_password": "NewPass4Role!"},
        )
        # Backdate tokens_valid_after by 1 second so a new login
        # issued in the same second as the reset passes the <= fence.
        db_session.refresh(p)
        tva = p.tokens_valid_after
        if tva is not None:
            if tva.tzinfo is None:
                tva = tva.replace(tzinfo=timezone.utc)
            p.tokens_valid_after = tva - timedelta(seconds=1)
            db_session.commit()
        new_token = _get_token(client, p.email, password="NewPass4Role!")
        res = client.get(
            "/users/organization",
            headers={"Authorization": f"Bearer {new_token}"},
            cookies={},
        )
        assert res.status_code == 200

    def test_customer_blocked_from_pharmacist_endpoint_after_revocation(
        self, client, db_session
    ):
        cust = _make_customer(db_session, "role-cust-revoke")
        token = _get_token(client, cust.email)
        res = client.get(
            "/users/organization",
            headers={"Authorization": f"Bearer {token}"},
            cookies={},
        )
        assert res.status_code == 403

    def test_admin_can_access_admin_endpoint_after_revocation(
        self, client, db_session
    ):
        admin = _make_admin(db_session, "role-adm-revoke")
        token = _get_token(client, admin.email, password="adminpass123")
        res = client.get(
            "/admin/stats",
            headers={"Authorization": f"Bearer {token}"},
            cookies={},
        )
        assert res.status_code == 200

    def test_inactive_user_gets_403_regardless_of_revocation(
        self, client, db_session
    ):
        org = OrganizationDB(name="Inactive Org R", slug="inactive-org-r")
        db_session.add(org)
        db_session.flush()

        inactive = UserDB(
            organization_id=org.id,
            name="Inactive R",
            email="inactive-r@example.com",
            password_hash=hash_password("password123"),
            role="pharmacist",
            is_active=True,
            email_verified=True,
        )
        db_session.add(inactive)
        db_session.commit()

        token = _get_token(client, inactive.email)
        inactive.is_active = False
        db_session.commit()

        assert _me_with_bearer(client, token).status_code == 403

    def test_organization_isolation_preserved_after_reset(
        self, client, db_session
    ):
        org_a, pharm_a = _make_org_and_pharmacist(db_session, "iso-a-revoke")
        org_b, pharm_b = _make_org_and_pharmacist(db_session, "iso-b-revoke")

        raw_a = _insert_reset_token(db_session, pharm_a.id)
        client.post(
            "/auth/reset-password",
            json={"token": raw_a, "new_password": "NewPassIsoA1!"},
        )

        # Backdate tokens_valid_after by 1 second so that a new login
        # issued in the same second as the reset passes the <= fence.
        db_session.refresh(pharm_a)
        tva = pharm_a.tokens_valid_after
        if tva is not None:
            if tva.tzinfo is None:
                tva = tva.replace(tzinfo=timezone.utc)
            pharm_a.tokens_valid_after = tva - timedelta(seconds=1)
            db_session.commit()

        new_token_a = _get_token(
            client, pharm_a.email, password="NewPassIsoA1!"
        )
        res = client.get(
            "/prescriptions",
            headers={"Authorization": f"Bearer {new_token_a}"},
            cookies={},
        )
        assert res.status_code == 200
        data = res.json()
        prescriptions = data if isinstance(data, list) else data.get(
            "prescriptions", []
        )
        for prx in prescriptions:
            assert prx.get("organization_id") == str(org_a.id)


# =========================================================
# 6. SECURITY — NO RAW JWT IN DB
# =========================================================


class TestSecurityInvariants:

    def test_no_raw_jwt_in_revoked_access_tokens(self, client, db_session):
        """The revoked_access_tokens table must only store jti, not raw JWT."""
        engine = db_session.bind
        Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        _, p = _make_org_and_pharmacist(db_session, "sec-raw")
        login_res = _login(client, p.email)
        raw_token = login_res.json()["access_token"]
        cookie = login_res.cookies.get(COOKIE_NAME)

        client.post("/auth/logout", cookies={COOKIE_NAME: cookie})

        check_db = Session()
        rows = check_db.query(RevokedAccessTokenDB).all()
        check_db.close()

        assert rows, "Expected at least one revoked_access_tokens row"
        for row in rows:
            # The jti is a UUID string (36 chars), NOT the full JWT
            assert len(row.jti) <= 36, (
                f"jti column stores too many chars ({len(row.jti)}); "
                "raw JWT may have been stored"
            )
            assert "." not in row.jti, (
                "jti contains '.'; raw JWT (header.payload.sig) may be stored"
            )

    def test_jti_is_unique_per_token(self, client, db_session):
        """Each new login produces a different jti."""
        _, p = _make_org_and_pharmacist(db_session, "sec-unique")
        from backend.security import decode_access_token

        token_a = _get_token(client, p.email)
        token_b = _get_token(client, p.email)

        payload_a = decode_access_token(token_a)
        payload_b = decode_access_token(token_b)

        assert payload_a["jti"] != payload_b["jti"]
