"""
Tests for Phase 3B operational workflow additions:

  - GET /prescriptions — review_status filter (server-side)
  - GET /prescriptions — search filter (server-side)
  - GET /prescriptions — status (pipeline) filter
  - GET /admin/stats
  - GET /users/organization/members

Tenant isolation and authorization are verified throughout.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base, get_db
from backend.main import app
from backend.models import OrganizationDB, PrescriptionDB, UserDB
from backend.security import hash_password


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


def _make_org(db_session, name: str, slug: str) -> OrganizationDB:
    org = OrganizationDB(name=name, slug=slug)
    db_session.add(org)
    db_session.flush()
    return org


def _make_pharmacist(db_session, org, email: str) -> UserDB:
    user = UserDB(
        organization_id=org.id,
        name="Test Pharmacist",
        email=email,
        password_hash=hash_password("password123"),
        role="pharmacist",
        is_active=True,
        email_verified=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


def _make_admin(db_session, email: str = "admin@example.com") -> UserDB:
    user = UserDB(
        organization_id=None,
        name="Platform Admin",
        email=email,
        password_hash=hash_password("adminpass"),
        role="admin",
        is_active=True,
        email_verified=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


def _make_prescription(
    db_session,
    org,
    prescription_id: str,
    review_status: str = "pending",
    status: str = "analyzed",
    file_name: str | None = None,
) -> PrescriptionDB:
    rx = PrescriptionDB(
        prescription_id=prescription_id,
        organization_id=org.id,
        status=status,
        review_status=review_status,
        file_name=file_name,
        safety_flags=[],
    )
    db_session.add(rx)
    db_session.flush()
    return rx


def _login(client, email: str, password: str = "password123") -> str:
    res = client.post("/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, f"Login failed: {res.text}"
    return res.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# =========================================================
# REVIEW_STATUS FILTER
# =========================================================


def test_review_status_filter_pending_returns_only_pending(client, db_session):
    """Server-side pending filter returns only pending prescriptions."""
    org = _make_org(db_session, "FilterOrg", "filter-org")
    pharmacist = _make_pharmacist(db_session, org, "pharm-filter@example.com")
    _make_prescription(db_session, org, "RX-PEND-1", review_status="pending")
    _make_prescription(db_session, org, "RX-PEND-2", review_status="pending")
    _make_prescription(db_session, org, "RX-VERIF-1", review_status="verified")
    _make_prescription(db_session, org, "RX-REJ-1", review_status="rejected")
    db_session.commit()

    token = _login(client, "pharm-filter@example.com")
    res = client.get("/prescriptions?review_status=pending", headers=_auth(token))

    assert res.status_code == 200
    ids = {r["prescription_id"] for r in res.json()}
    assert "RX-PEND-1" in ids
    assert "RX-PEND-2" in ids
    assert "RX-VERIF-1" not in ids
    assert "RX-REJ-1" not in ids


def test_review_status_filter_under_review(client, db_session):
    """under_review filter returns only under_review prescriptions."""
    org = _make_org(db_session, "UROrg", "ur-org")
    pharmacist = _make_pharmacist(db_session, org, "pharm-ur@example.com")
    _make_prescription(db_session, org, "RX-UR-1", review_status="under_review")
    _make_prescription(db_session, org, "RX-PEND-3", review_status="pending")
    db_session.commit()

    token = _login(client, "pharm-ur@example.com")
    res = client.get("/prescriptions?review_status=under_review", headers=_auth(token))

    assert res.status_code == 200
    ids = {r["prescription_id"] for r in res.json()}
    assert "RX-UR-1" in ids
    assert "RX-PEND-3" not in ids


def test_review_status_filter_verified(client, db_session):
    """verified filter returns only verified prescriptions."""
    org = _make_org(db_session, "VOrg", "v-org")
    pharmacist = _make_pharmacist(db_session, org, "pharm-v@example.com")
    _make_prescription(db_session, org, "RX-V-1", review_status="verified")
    _make_prescription(db_session, org, "RX-P-1", review_status="pending")
    db_session.commit()

    token = _login(client, "pharm-v@example.com")
    res = client.get("/prescriptions?review_status=verified", headers=_auth(token))

    assert res.status_code == 200
    ids = {r["prescription_id"] for r in res.json()}
    assert "RX-V-1" in ids
    assert "RX-P-1" not in ids


def test_review_status_invalid_value_returns_400(client, db_session):
    """An invalid review_status value returns HTTP 400."""
    org = _make_org(db_session, "BadOrg", "bad-org")
    pharmacist = _make_pharmacist(db_session, org, "pharm-bad@example.com")
    db_session.commit()

    token = _login(client, "pharm-bad@example.com")
    res = client.get("/prescriptions?review_status=invalid_status", headers=_auth(token))

    assert res.status_code == 400


def test_review_status_filter_org_isolation(client, db_session):
    """Pharmacist A cannot see Org B prescriptions even with matching review_status."""
    org_a = _make_org(db_session, "OrgA", "org-a")
    org_b = _make_org(db_session, "OrgB", "org-b")
    pharm_a = _make_pharmacist(db_session, org_a, "pharm-a@example.com")
    pharm_b = _make_pharmacist(db_session, org_b, "pharm-b@example.com")

    _make_prescription(db_session, org_a, "RX-A-PEND", review_status="pending")
    _make_prescription(db_session, org_b, "RX-B-PEND", review_status="pending")
    db_session.commit()

    token_a = _login(client, "pharm-a@example.com")
    res = client.get("/prescriptions?review_status=pending", headers=_auth(token_a))

    assert res.status_code == 200
    ids = {r["prescription_id"] for r in res.json()}
    assert "RX-A-PEND" in ids
    assert "RX-B-PEND" not in ids


def test_review_status_filter_pagination(client, db_session):
    """Pagination works correctly with review_status filter."""
    org = _make_org(db_session, "PagOrg", "pag-org")
    pharmacist = _make_pharmacist(db_session, org, "pharm-pag@example.com")
    for i in range(5):
        _make_prescription(db_session, org, f"RX-PAG-{i}", review_status="pending")
    _make_prescription(db_session, org, "RX-PAG-V", review_status="verified")
    db_session.commit()

    token = _login(client, "pharm-pag@example.com")

    # First page: 2 items
    res = client.get(
        "/prescriptions?review_status=pending&skip=0&limit=2",
        headers=_auth(token),
    )
    assert res.status_code == 200
    page1 = res.json()
    assert len(page1) == 2

    # Second page: next 2 items
    res2 = client.get(
        "/prescriptions?review_status=pending&skip=2&limit=2",
        headers=_auth(token),
    )
    assert res2.status_code == 200
    page2 = res2.json()
    assert len(page2) == 2

    # Pages must not overlap
    ids1 = {r["prescription_id"] for r in page1}
    ids2 = {r["prescription_id"] for r in page2}
    assert ids1.isdisjoint(ids2)

    # Verified prescription never appears in any page
    all_ids = ids1 | ids2
    assert "RX-PAG-V" not in all_ids


# =========================================================
# SEARCH FILTER
# =========================================================


def test_search_by_prescription_id(client, db_session):
    """Search by prescription_id substring is server-side."""
    org = _make_org(db_session, "SearchOrg", "search-org")
    pharmacist = _make_pharmacist(db_session, org, "pharm-search@example.com")
    _make_prescription(db_session, org, "UNIQUE-ABC-001")
    _make_prescription(db_session, org, "COMPLETELY-DIFFERENT-999")
    db_session.commit()

    token = _login(client, "pharm-search@example.com")
    res = client.get("/prescriptions?search=UNIQUE-ABC", headers=_auth(token))

    assert res.status_code == 200
    ids = {r["prescription_id"] for r in res.json()}
    assert "UNIQUE-ABC-001" in ids
    assert "COMPLETELY-DIFFERENT-999" not in ids


def test_search_by_file_name(client, db_session):
    """Search by file_name substring is server-side."""
    org = _make_org(db_session, "FileOrg", "file-org")
    pharmacist = _make_pharmacist(db_session, org, "pharm-file@example.com")
    _make_prescription(db_session, org, "RX-FILE-1", file_name="scan_2024_01_15.jpg")
    _make_prescription(db_session, org, "RX-FILE-2", file_name="other_document.pdf")
    db_session.commit()

    token = _login(client, "pharm-file@example.com")
    res = client.get("/prescriptions?search=scan_2024", headers=_auth(token))

    assert res.status_code == 200
    ids = {r["prescription_id"] for r in res.json()}
    assert "RX-FILE-1" in ids
    assert "RX-FILE-2" not in ids


def test_search_org_isolation(client, db_session):
    """Search cannot retrieve prescriptions from another organization."""
    org_x = _make_org(db_session, "OrgX", "org-x")
    org_y = _make_org(db_session, "OrgY", "org-y")
    pharm_x = _make_pharmacist(db_session, org_x, "pharm-x@example.com")
    _make_prescription(db_session, org_x, "SHARED-TERM-001")
    _make_prescription(db_session, org_y, "SHARED-TERM-002")
    db_session.commit()

    token_x = _login(client, "pharm-x@example.com")
    res = client.get("/prescriptions?search=SHARED-TERM", headers=_auth(token_x))

    assert res.status_code == 200
    ids = {r["prescription_id"] for r in res.json()}
    assert "SHARED-TERM-001" in ids
    assert "SHARED-TERM-002" not in ids


def test_search_combined_with_review_status(client, db_session):
    """Search and review_status filters can be combined."""
    org = _make_org(db_session, "ComboOrg", "combo-org")
    pharmacist = _make_pharmacist(db_session, org, "pharm-combo@example.com")
    _make_prescription(db_session, org, "COMBO-PEND-001", review_status="pending")
    _make_prescription(db_session, org, "COMBO-VERIF-002", review_status="verified")
    _make_prescription(db_session, org, "OTHER-PEND-003", review_status="pending")
    db_session.commit()

    token = _login(client, "pharm-combo@example.com")
    res = client.get(
        "/prescriptions?search=COMBO&review_status=pending",
        headers=_auth(token),
    )

    assert res.status_code == 200
    ids = {r["prescription_id"] for r in res.json()}
    assert "COMBO-PEND-001" in ids
    assert "COMBO-VERIF-002" not in ids  # different review_status
    assert "OTHER-PEND-003" not in ids  # doesn't match search


# =========================================================
# PIPELINE STATUS FILTER
# =========================================================


def test_pipeline_status_filter_analyzed(client, db_session):
    """status=analyzed filter returns only analyzed prescriptions."""
    org = _make_org(db_session, "PipeOrg", "pipe-org")
    pharmacist = _make_pharmacist(db_session, org, "pharm-pipe@example.com")
    _make_prescription(db_session, org, "RX-ANA-1", status="analyzed")
    _make_prescription(db_session, org, "RX-UPL-1", status="uploaded")
    db_session.commit()

    token = _login(client, "pharm-pipe@example.com")
    res = client.get("/prescriptions?status=analyzed", headers=_auth(token))

    assert res.status_code == 200
    ids = {r["prescription_id"] for r in res.json()}
    assert "RX-ANA-1" in ids
    assert "RX-UPL-1" not in ids


def test_pipeline_status_invalid_returns_400(client, db_session):
    """An invalid pipeline status returns HTTP 400."""
    org = _make_org(db_session, "PipeInvOrg", "pipe-inv-org")
    pharmacist = _make_pharmacist(db_session, org, "pharm-pinv@example.com")
    db_session.commit()

    token = _login(client, "pharm-pinv@example.com")
    res = client.get("/prescriptions?status=processing", headers=_auth(token))
    assert res.status_code == 400


# =========================================================
# REVIEW_STATUS IN RESPONSE SCHEMA
# =========================================================


def test_prescription_list_includes_review_status(client, db_session):
    """Each prescription in the list response includes review_status."""
    org = _make_org(db_session, "SchemaOrg", "schema-org")
    pharmacist = _make_pharmacist(db_session, org, "pharm-schema@example.com")
    _make_prescription(db_session, org, "RX-SCH-1", review_status="verified")
    db_session.commit()

    token = _login(client, "pharm-schema@example.com")
    res = client.get("/prescriptions", headers=_auth(token))

    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert "review_status" in data[0]
    assert data[0]["review_status"] == "verified"


# =========================================================
# ADMIN STATS
# =========================================================


def test_admin_stats_returns_correct_counts(client, db_session):
    """GET /admin/stats returns real counts for users, orgs, prescriptions, reviews."""
    org = _make_org(db_session, "AdminStatsOrg", "admin-stats-org")
    pharmacist = _make_pharmacist(db_session, org, "pharm-stats@example.com")
    admin = _make_admin(db_session, "admin-stats@example.com")
    _make_prescription(db_session, org, "RX-STAT-PEND-1", review_status="pending")
    _make_prescription(db_session, org, "RX-STAT-PEND-2", review_status="pending")
    _make_prescription(db_session, org, "RX-STAT-VERIF", review_status="verified")
    db_session.commit()

    token = _login(client, "admin-stats@example.com", "adminpass")
    res = client.get("/admin/stats", headers=_auth(token))

    assert res.status_code == 200
    data = res.json()

    assert "total_users" in data
    assert "total_organizations" in data
    assert "total_prescriptions" in data
    assert "pending_reviews" in data
    assert "under_review" in data

    # Counts must be real integers >= 0
    assert isinstance(data["total_users"], int)
    assert data["total_users"] >= 2  # pharmacist + admin
    assert data["total_organizations"] >= 1
    assert data["total_prescriptions"] >= 3
    assert data["pending_reviews"] >= 2


def test_admin_stats_denied_for_pharmacist(client, db_session):
    """Pharmacist cannot access /admin/stats."""
    org = _make_org(db_session, "DeniedOrg", "denied-org")
    pharmacist = _make_pharmacist(db_session, org, "pharm-denied@example.com")
    db_session.commit()

    token = _login(client, "pharm-denied@example.com")
    res = client.get("/admin/stats", headers=_auth(token))
    assert res.status_code == 403


def test_admin_stats_denied_unauthenticated(client, db_session):
    """Unauthenticated request to /admin/stats returns 401."""
    res = client.get("/admin/stats")
    assert res.status_code == 401


# =========================================================
# ORGANIZATION MEMBERS
# =========================================================


def test_members_returns_own_org_pharmacists(client, db_session):
    """GET /users/organization/members returns pharmacists in current org."""
    org = _make_org(db_session, "MemberOrg", "member-org")
    pharm1 = _make_pharmacist(db_session, org, "pharm1-mem@example.com")
    pharm2 = _make_pharmacist(db_session, org, "pharm2-mem@example.com")
    db_session.commit()

    token = _login(client, "pharm1-mem@example.com")
    res = client.get("/users/organization/members", headers=_auth(token))

    assert res.status_code == 200
    data = res.json()
    emails = {m["email"] for m in data}
    assert "pharm1-mem@example.com" in emails
    assert "pharm2-mem@example.com" in emails


def test_members_cross_org_isolation(client, db_session):
    """Pharmacist from Org A cannot see members of Org B."""
    org_a = _make_org(db_session, "MemOrgA", "mem-org-a")
    org_b = _make_org(db_session, "MemOrgB", "mem-org-b")
    pharm_a = _make_pharmacist(db_session, org_a, "pharm-mema@example.com")
    pharm_b = _make_pharmacist(db_session, org_b, "pharm-memb@example.com")
    db_session.commit()

    token_a = _login(client, "pharm-mema@example.com")
    res = client.get("/users/organization/members", headers=_auth(token_a))

    assert res.status_code == 200
    emails = {m["email"] for m in res.json()}
    assert "pharm-mema@example.com" in emails
    assert "pharm-memb@example.com" not in emails


def test_members_excludes_customers(client, db_session):
    """Customer accounts do not appear in the member roster."""
    org = _make_org(db_session, "CustExcludeOrg", "cust-exclude-org")
    pharmacist = _make_pharmacist(db_session, org, "pharm-custex@example.com")

    # Create a customer-role user in the same org
    customer_user = UserDB(
        organization_id=org.id,
        name="Customer Person",
        email="customer-mem@example.com",
        password_hash=hash_password("pass1234"),
        role="customer",
        is_active=True,
        email_verified=True,
    )
    db_session.add(customer_user)
    db_session.commit()

    token = _login(client, "pharm-custex@example.com")
    res = client.get("/users/organization/members", headers=_auth(token))

    assert res.status_code == 200
    roles = {m["role"] for m in res.json()}
    assert "customer" not in roles


def test_members_no_sensitive_fields(client, db_session):
    """Member response must not contain password_hash or token fields."""
    org = _make_org(db_session, "SecureOrg", "secure-org")
    pharmacist = _make_pharmacist(db_session, org, "pharm-secure@example.com")
    db_session.commit()

    token = _login(client, "pharm-secure@example.com")
    res = client.get("/users/organization/members", headers=_auth(token))

    assert res.status_code == 200
    for member in res.json():
        assert "password_hash" not in member
        assert "email_verification_token_hash" not in member
        assert "email_verification_expires_at" not in member

        # Expected safe fields must be present
        assert "id" in member
        assert "name" in member
        assert "email" in member
        assert "is_active" in member
        assert "email_verified" in member


def test_members_denied_for_customer_role(client, db_session):
    """A customer-role user cannot access /users/organization/members."""
    org = _make_org(db_session, "CustDeniedOrg", "cust-denied-org")

    # Customer user — use password "pass1234" explicitly
    customer_user = UserDB(
        organization_id=org.id,
        name="Customer",
        email="cust-denied@example.com",
        password_hash=hash_password("pass1234"),
        role="customer",
        is_active=True,
        email_verified=True,
    )
    db_session.add(customer_user)
    db_session.commit()

    token = _login(client, "cust-denied@example.com", "pass1234")
    res = client.get("/users/organization/members", headers=_auth(token))
    assert res.status_code == 403


def test_members_denied_unauthenticated(client, db_session):
    """Unauthenticated request to /users/organization/members returns 401."""
    res = client.get("/users/organization/members")
    assert res.status_code == 401
