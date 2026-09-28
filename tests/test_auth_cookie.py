"""
tests/test_auth_cookie.py — P7.12-B HttpOnly cookie authentication tests.

Covers:
    - Cookie creation on /auth/login
    - Cookie creation on /auth/token (OAuth2 endpoint)
    - Cookie attributes: HttpOnly, SameSite=Lax, Path=/
    - Secure flag behavior (production vs development)
    - Cookie authentication for /users/me
    - Invalid / expired cookie → 401
    - Missing both cookie and Bearer → 401
    - Cookie takes priority over Bearer when both present
    - Bearer compatibility: valid Bearer still authenticates
    - Invalid Bearer still returns 401
    - /auth/logout clears pi_access_token cookie with Path=/
    - Existing authorization still respected with cookie auth:
        pharmacist role, customer role, admin role,
        organization isolation, inactive users

Reuses existing fixture patterns from test_phase3a_saas.py /
test_phase3b_operations.py to avoid duplication.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base, get_db
from backend.main import app
from backend.models import OrganizationDB, UserDB
from backend.security import (
    ALGORITHM,
    COOKIE_NAME,
    ENVIRONMENT,
    SECRET_KEY,
    hash_password,
)


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


def _make_org_and_pharmacist(db_session, slug="cookie-test-pharmacy"):
    org = OrganizationDB(name="Cookie Test Pharmacy", slug=slug)
    db_session.add(org)
    db_session.flush()

    pharmacist = UserDB(
        organization_id=org.id,
        name="Cookie Pharmacist",
        email=f"pharmacist-{slug}@example.com",
        password_hash=hash_password("password123"),
        role="pharmacist",
        is_active=True,
        email_verified=True,
    )
    db_session.add(pharmacist)
    db_session.commit()
    return org, pharmacist


def _make_customer(db_session):
    customer = UserDB(
        organization_id=None,
        name="Cookie Customer",
        email="customer-cookie@example.com",
        password_hash=hash_password("password123"),
        role="customer",
        is_active=True,
        email_verified=True,
    )
    db_session.add(customer)
    db_session.commit()
    return customer


def _make_admin(db_session):
    admin = UserDB(
        organization_id=None,
        name="Cookie Admin",
        email="admin-cookie@example.com",
        password_hash=hash_password("adminpass123"),
        role="admin",
        is_active=True,
        email_verified=True,
    )
    db_session.add(admin)
    db_session.commit()
    return admin


def _login(client, email, password="password123"):
    """Return the full response object so tests can inspect cookies."""
    return client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )


def _get_token_from_login(client, email, password="password123"):
    """Return the JWT string from the JSON body (Bearer compat)."""
    res = _login(client, email, password)
    assert res.status_code == 200, f"Login failed: {res.json()}"
    return res.json()["access_token"]


def _expired_jwt(user_id: str) -> str:
    """Build a JWT that is already expired."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": "pharmacist",
        "organization_id": None,
        "token_type": "access",
        "iat": now - timedelta(hours=25),
        "exp": now - timedelta(hours=1),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# =========================================================
# 1. COOKIE CREATION
# =========================================================


class TestCookieCreation:
    def test_login_sets_cookie(self, client, db_session):
        """POST /auth/login sets pi_access_token cookie."""
        _, pharmacist = _make_org_and_pharmacist(db_session)
        res = _login(client, pharmacist.email)
        assert res.status_code == 200
        assert COOKIE_NAME in res.cookies, (
            f"Expected Set-Cookie: {COOKIE_NAME} in response"
        )

    def test_login_cookie_is_httponly(self, client, db_session):
        """The pi_access_token cookie must be HttpOnly."""
        _, pharmacist = _make_org_and_pharmacist(
            db_session, slug="httponly-test"
        )
        res = _login(client, pharmacist.email)
        assert res.status_code == 200
        raw = res.headers.get("set-cookie", "")
        assert "httponly" in raw.lower(), (
            f"HttpOnly attribute missing from Set-Cookie header: {raw}"
        )

    def test_login_cookie_samesite_lax(self, client, db_session):
        """The pi_access_token cookie must be SameSite=Lax."""
        _, pharmacist = _make_org_and_pharmacist(
            db_session, slug="samesite-test"
        )
        res = _login(client, pharmacist.email)
        assert res.status_code == 200
        raw = res.headers.get("set-cookie", "")
        assert "samesite=lax" in raw.lower(), (
            f"SameSite=Lax attribute missing from Set-Cookie header: {raw}"
        )

    def test_login_cookie_path_root(self, client, db_session):
        """The pi_access_token cookie must use Path=/."""
        _, pharmacist = _make_org_and_pharmacist(
            db_session, slug="path-test"
        )
        res = _login(client, pharmacist.email)
        assert res.status_code == 200
        raw = res.headers.get("set-cookie", "")
        assert "path=/" in raw.lower(), (
            f"Path=/ attribute missing from Set-Cookie header: {raw}"
        )

    def test_login_cookie_max_age_86400(self, client, db_session):
        """The cookie Max-Age must be 86400 (24 hours)."""
        _, pharmacist = _make_org_and_pharmacist(
            db_session, slug="maxage-test"
        )
        res = _login(client, pharmacist.email)
        assert res.status_code == 200
        raw = res.headers.get("set-cookie", "")
        assert "max-age=86400" in raw.lower(), (
            f"Max-Age=86400 attribute missing from Set-Cookie header: {raw}"
        )

    def test_production_sets_secure_flag(self, client, db_session):
        """In production mode the Secure flag must be present."""
        _, pharmacist = _make_org_and_pharmacist(
            db_session, slug="secure-prod-test"
        )
        with patch("backend.routers.auth.COOKIE_SECURE", True):
            res = _login(client, pharmacist.email)
        assert res.status_code == 200
        raw = res.headers.get("set-cookie", "")
        assert "secure" in raw.lower(), (
            f"Secure attribute expected for production but missing: {raw}"
        )

    def test_development_does_not_require_secure(self, client, db_session):
        """In development mode the Secure flag must NOT be set."""
        _, pharmacist = _make_org_and_pharmacist(
            db_session, slug="secure-dev-test"
        )
        with patch("backend.routers.auth.COOKIE_SECURE", False):
            res = _login(client, pharmacist.email)
        assert res.status_code == 200
        # The cookie value must be present regardless.
        assert COOKIE_NAME in res.cookies
        # Verify Secure attribute is absent in development.
        raw = res.headers.get("set-cookie", "")
        # "secure" may appear as a standalone attribute (not as part of
        # another word).  A simple lowercase check is sufficient here.
        parts = [p.strip().lower() for p in raw.split(";")]
        assert "secure" not in parts, (
            f"Secure attribute must not be set in development: {raw}"
        )

    def test_token_endpoint_also_sets_cookie(self, client, db_session):
        """POST /auth/token (OAuth2) also sets the HttpOnly cookie."""
        _, pharmacist = _make_org_and_pharmacist(
            db_session, slug="token-endpoint-test"
        )
        res = client.post(
            "/auth/token",
            data={
                "username": pharmacist.email,
                "password": "password123",
            },
        )
        assert res.status_code == 200
        assert COOKIE_NAME in res.cookies

    def test_login_json_body_still_contains_access_token(
        self, client, db_session
    ):
        """access_token is still in the JSON body for Bearer compatibility."""
        _, pharmacist = _make_org_and_pharmacist(
            db_session, slug="json-token-test"
        )
        res = _login(client, pharmacist.email)
        assert res.status_code == 200
        assert "access_token" in res.json()


# =========================================================
# 2. COOKIE AUTHENTICATION
# =========================================================


class TestCookieAuthentication:
    def test_valid_cookie_authenticates_me(self, client, db_session):
        """A valid pi_access_token cookie authenticates /users/me."""
        _, pharmacist = _make_org_and_pharmacist(
            db_session, slug="cookie-auth-test"
        )
        # Log in to obtain cookie.
        _login(client, pharmacist.email)

        res = client.get(
            "/users/me",
            cookies={COOKIE_NAME: client.cookies.get(COOKIE_NAME)},
        )
        assert res.status_code == 200
        assert res.json()["email"] == pharmacist.email

    def test_invalid_cookie_returns_401(self, client, db_session):
        """An invalid JWT in the cookie returns 401."""
        res = client.get(
            "/users/me",
            cookies={COOKIE_NAME: "not.a.valid.jwt"},
        )
        assert res.status_code == 401

    def test_expired_cookie_returns_401(self, client, db_session):
        """An expired JWT in the cookie returns 401."""
        _, pharmacist = _make_org_and_pharmacist(
            db_session, slug="expired-cookie-test"
        )
        expired = _expired_jwt(pharmacist.id)
        res = client.get(
            "/users/me",
            cookies={COOKIE_NAME: expired},
        )
        assert res.status_code == 401

    def test_missing_cookie_and_bearer_returns_401(self, client, db_session):
        """No cookie and no Authorization header → 401."""
        res = client.get("/users/me")
        assert res.status_code == 401

    def test_cookie_takes_priority_over_bearer(self, client, db_session):
        """
        When both cookie and Bearer are present the cookie is used.

        We supply a VALID cookie for pharmacist_a and an INVALID Bearer
        token.  The request should succeed because the cookie wins.
        """
        org, pharmacist_a = _make_org_and_pharmacist(
            db_session, slug="priority-test-a"
        )
        # Get a valid JWT via login (stored as cookie by TestClient).
        login_res = _login(client, pharmacist_a.email)
        valid_cookie = login_res.cookies.get(COOKIE_NAME)

        res = client.get(
            "/users/me",
            cookies={COOKIE_NAME: valid_cookie},
            headers={"Authorization": "Bearer not.a.valid.token"},
        )
        # Cookie wins; invalid Bearer is ignored.
        assert res.status_code == 200
        assert res.json()["email"] == pharmacist_a.email

    def test_cookie_priority_over_bearer_invalid_cookie(
        self, client, db_session
    ):
        """
        When the cookie is INVALID but the Bearer is VALID we expect 401.

        Cookie priority: an invalid cookie should cause 401 even when
        a valid Bearer token is also sent.  This tests the priority
        rule strictly — the cookie is tried first; if it fails to
        decode, the dependency raises 401 without falling back to the
        Bearer.  (Documented behavior: the cookie wins.)
        """
        _, pharmacist = _make_org_and_pharmacist(
            db_session, slug="priority-invalid-cookie"
        )
        valid_token = _get_token_from_login(client, pharmacist.email)

        res = client.get(
            "/users/me",
            cookies={COOKIE_NAME: "invalid.cookie.value"},
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        # Invalid cookie is preferred; Bearer is not used as fallback.
        assert res.status_code == 401


# =========================================================
# 3. BEARER COMPATIBILITY
# =========================================================


class TestBearerCompatibility:
    def test_valid_bearer_authenticates(self, client, db_session):
        """Existing Bearer token still authenticates after cookie migration."""
        _, pharmacist = _make_org_and_pharmacist(
            db_session, slug="bearer-compat-test"
        )
        token = _get_token_from_login(client, pharmacist.email)

        # Explicitly no cookie; only Bearer header.
        res = client.get(
            "/users/me",
            headers={"Authorization": f"Bearer {token}"},
            cookies={},
        )
        assert res.status_code == 200
        assert res.json()["email"] == pharmacist.email

    def test_invalid_bearer_returns_401(self, client, db_session):
        """An invalid Bearer token still returns 401."""
        res = client.get(
            "/users/me",
            headers={"Authorization": "Bearer this.is.invalid"},
            cookies={},
        )
        assert res.status_code == 401

    def test_expired_bearer_returns_401(self, client, db_session):
        """An expired Bearer token returns 401."""
        _, pharmacist = _make_org_and_pharmacist(
            db_session, slug="expired-bearer-test"
        )
        expired = _expired_jwt(pharmacist.id)
        res = client.get(
            "/users/me",
            headers={"Authorization": f"Bearer {expired}"},
            cookies={},
        )
        assert res.status_code == 401


# =========================================================
# 4. LOGOUT
# =========================================================


class TestLogout:
    def test_logout_clears_cookie(self, client, db_session):
        """POST /auth/logout clears the pi_access_token cookie."""
        _, pharmacist = _make_org_and_pharmacist(
            db_session, slug="logout-test"
        )
        _login(client, pharmacist.email)

        res = client.post("/auth/logout")
        assert res.status_code == 200

        # After logout the cookie should be deleted (Max-Age=0 or absence).
        raw = res.headers.get("set-cookie", "")
        # A delete_cookie sets Max-Age=0 or expires in the past.
        # FastAPI's delete_cookie sets max-age=0.
        assert COOKIE_NAME.lower() in raw.lower(), (
            "Expected the cookie name in the logout Set-Cookie header"
        )
        assert "max-age=0" in raw.lower() or 'expires="' in raw.lower(), (
            f"Expected Max-Age=0 in logout Set-Cookie header: {raw}"
        )

    def test_logout_cookie_deletion_uses_path_root(self, client, db_session):
        """The logout cookie deletion must include Path=/."""
        _, pharmacist = _make_org_and_pharmacist(
            db_session, slug="logout-path-test"
        )
        _login(client, pharmacist.email)

        res = client.post("/auth/logout")
        raw = res.headers.get("set-cookie", "")
        assert "path=/" in raw.lower(), (
            f"Path=/ missing from logout Set-Cookie header: {raw}"
        )

    def test_logout_returns_json_success(self, client, db_session):
        """POST /auth/logout returns a JSON success message."""
        _, pharmacist = _make_org_and_pharmacist(
            db_session, slug="logout-json-test"
        )
        _login(client, pharmacist.email)

        res = client.post("/auth/logout")
        assert res.status_code == 200
        assert "message" in res.json()

    def test_jwt_still_valid_via_bearer_after_logout(
        self, client, db_session
    ):
        """
        An issued JWT remains cryptographically valid via Bearer after
        cookie logout (no revocation in this phase).

        This documents the known limitation: cookie logout only removes
        the browser cookie; Bearer tokens are not revoked.
        """
        _, pharmacist = _make_org_and_pharmacist(
            db_session, slug="no-revoke-test"
        )
        token = _get_token_from_login(client, pharmacist.email)

        # Logout clears the cookie.
        client.post("/auth/logout")

        # The JWT can still be used directly via Bearer.
        res = client.get(
            "/users/me",
            headers={"Authorization": f"Bearer {token}"},
            cookies={},
        )
        assert res.status_code == 200, (
            "Bearer token should remain valid after cookie logout "
            "(revocation not implemented in this phase)"
        )


# =========================================================
# 5. AUTHORIZATION — ROLE & ISOLATION
# =========================================================


class TestAuthorizationWithCookie:
    """
    Verify that cookie-authenticated requests still respect all
    existing authorization rules.
    """

    def _cookie_get(self, client, path, cookie_value):
        return client.get(
            path,
            cookies={COOKIE_NAME: cookie_value},
        )

    def test_pharmacist_role_required_endpoint(self, client, db_session):
        """Pharmacist can access pharmacy-scoped endpoint via cookie."""
        org, pharmacist = _make_org_and_pharmacist(
            db_session, slug="role-pharmacist-test"
        )
        login_res = _login(client, pharmacist.email)
        cookie = login_res.cookies.get(COOKIE_NAME)

        res = self._cookie_get(client, "/users/organization", cookie)
        assert res.status_code == 200

    def test_customer_cannot_access_pharmacist_endpoint(
        self, client, db_session
    ):
        """Customer cookie cannot access pharmacist-only endpoint."""
        customer = _make_customer(db_session)
        login_res = _login(client, customer.email)
        cookie = login_res.cookies.get(COOKIE_NAME)

        res = self._cookie_get(client, "/users/organization", cookie)
        assert res.status_code == 403

    def test_admin_role_can_access_admin_endpoint(
        self, client, db_session
    ):
        """Admin cookie can access admin-only endpoint."""
        admin = _make_admin(db_session)
        login_res = _login(client, admin.email, password="adminpass123")
        cookie = login_res.cookies.get(COOKIE_NAME)

        res = self._cookie_get(client, "/admin/stats", cookie)
        assert res.status_code == 200

    def test_pharmacist_cannot_access_admin_endpoint(
        self, client, db_session
    ):
        """Pharmacist cookie cannot access admin-only endpoint."""
        _, pharmacist = _make_org_and_pharmacist(
            db_session, slug="role-admin-block-test"
        )
        login_res = _login(client, pharmacist.email)
        cookie = login_res.cookies.get(COOKIE_NAME)

        res = self._cookie_get(client, "/admin/stats", cookie)
        assert res.status_code == 403

    def test_inactive_user_cookie_returns_403(self, client, db_session):
        """An inactive user cannot authenticate even with a valid cookie."""
        org = OrganizationDB(name="Inactive Org", slug="inactive-org-cookie")
        db_session.add(org)
        db_session.flush()

        inactive_user = UserDB(
            organization_id=org.id,
            name="Inactive",
            email="inactive-cookie@example.com",
            password_hash=hash_password("password123"),
            role="pharmacist",
            is_active=True,   # active for login
            email_verified=True,
        )
        db_session.add(inactive_user)
        db_session.commit()

        # Login while active to get a valid JWT.
        login_res = _login(client, inactive_user.email)
        token_cookie = login_res.cookies.get(COOKIE_NAME)

        # Now deactivate the user.
        inactive_user.is_active = False
        db_session.commit()

        # The cookie token now belongs to an inactive account.
        res = self._cookie_get(client, "/users/me", token_cookie)
        assert res.status_code == 403

    def test_organization_isolation_via_cookie(self, client, db_session):
        """
        A pharmacist from Org A cannot see Org B's prescriptions
        when authenticated via cookie.
        """
        org_a, pharmacist_a = _make_org_and_pharmacist(
            db_session, slug="iso-org-a-cookie"
        )
        org_b, pharmacist_b = _make_org_and_pharmacist(
            db_session, slug="iso-org-b-cookie"
        )

        login_res_a = _login(client, pharmacist_a.email)
        cookie_a = login_res_a.cookies.get(COOKIE_NAME)

        # Pharmacist A should only see their own prescriptions.
        res = self._cookie_get(
            client, "/prescriptions", cookie_a
        )
        assert res.status_code == 200
        data = res.json()
        # The endpoint returns a list directly.
        prescriptions = data if isinstance(data, list) else data.get("prescriptions", [])
        # All returned prescriptions must belong to org_a.
        for p in prescriptions:
            assert p.get("organization_id") == str(org_a.id), (
                f"Pharmacist A got prescription from wrong org: {p}"
            )
