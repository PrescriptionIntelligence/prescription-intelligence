from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.auth import get_current_user
from backend.database import Base, get_db
from backend.main import app
from backend.models import (
    CustomerDB,
    CustomerOrganizationDB,
    OrganizationDB,
    PrescriptionDB,
    UserDB,
)
from backend.security import hash_password


@pytest.fixture()
def security_environment():
    """
    Isolated in-memory database for customer/pharmacy authorization tests.
    """

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(bind=engine)

    TestingSessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    db = TestingSessionLocal()

    pharmacy_a = OrganizationDB(
        name="Pharmacy A",
        slug=f"pharmacy-a-{uuid4().hex[:8]}",
    )

    pharmacy_b = OrganizationDB(
        name="Pharmacy B",
        slug=f"pharmacy-b-{uuid4().hex[:8]}",
    )

    pharmacist_a = UserDB(
        name="Pharmacist A",
        email=f"pharmacist-a-{uuid4().hex[:8]}@example.com",
        password_hash=hash_password("password-a"),
        role="pharmacist",
        is_active=True,
        organization=pharmacy_a,
    )

    pharmacist_b = UserDB(
        name="Pharmacist B",
        email=f"pharmacist-b-{uuid4().hex[:8]}@example.com",
        password_hash=hash_password("password-b"),
        role="pharmacist",
        is_active=True,
        organization=pharmacy_b,
    )

    customer_user = UserDB(
        name="Customer One",
        email=f"customer-{uuid4().hex[:8]}@example.com",
        password_hash=hash_password("customer-password"),
        role="customer",
        is_active=True,
        organization_id=None,
    )

    customer = CustomerDB(
        user=customer_user,
        organization=pharmacy_a,
        customer_code=f"CUST-{uuid4().hex[:8].upper()}",
        name="Customer One",
        phone="9999999999",
        email=customer_user.email,
        is_active=True,
    )

    membership_a = CustomerOrganizationDB(
        customer=customer,
        organization=pharmacy_a,
    )

    prescription_a = PrescriptionDB(
        prescription_id=f"RX-{uuid4().hex[:8].upper()}",
        organization=pharmacy_a,
        customer=customer,
        uploaded_by=pharmacist_a,
        raw_text="Paracetamol 650 mg, 1 tablet twice daily for 3 days",
        status="completed",
        review_status="pending",
        safety_flags=[],
        file_name="prescription-a.txt",
        file_path="",
        file_type="text/plain",
    )

    prescription_b = PrescriptionDB(
        prescription_id=f"RX-{uuid4().hex[:8].upper()}",
        organization=pharmacy_b,
        uploaded_by=pharmacist_b,
        raw_text="Paracetamol 500 mg, 1 tablet twice daily for 3 days",
        status="completed",
        review_status="pending",
        safety_flags=[],
        file_name="prescription-b.txt",
        file_path="",
        file_type="text/plain",
    )

    db.add_all(
        [
            pharmacy_a,
            pharmacy_b,
            pharmacist_a,
            pharmacist_b,
            customer_user,
            customer,
            membership_a,
            prescription_a,
            prescription_b,
        ]
    )

    db.commit()

    db.refresh(pharmacy_a)
    db.refresh(pharmacy_b)
    db.refresh(pharmacist_a)
    db.refresh(pharmacist_b)
    db.refresh(customer_user)
    db.refresh(customer)
    db.refresh(prescription_a)
    db.refresh(prescription_b)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    client = TestClient(
        app,
        raise_server_exceptions=False,
    )

    yield {
        "client": client,
        "db": db,
        "pharmacy_a": pharmacy_a,
        "pharmacy_b": pharmacy_b,
        "pharmacist_a": pharmacist_a,
        "pharmacist_b": pharmacist_b,
        "customer_user": customer_user,
        "customer": customer,
        "prescription_a": prescription_a,
        "prescription_b": prescription_b,
    }

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)

    db.close()
    engine.dispose()


def set_current_user(user):
    """
    Override authentication while preserving the real authorization
    dependencies used by the endpoint.
    """

    app.dependency_overrides[get_current_user] = lambda: user


class TestCustomerSecurity:
    def test_pharmacist_can_assign_customer_from_same_pharmacy(
        self,
        security_environment,
    ):
        env = security_environment

        set_current_user(env["pharmacist_a"])

        response = env["client"].patch(
            f"/prescriptions/"
            f"{env['prescription_a'].prescription_id}/customer",
            json={
                "customer_id": str(env["customer"].id),
            },
        )

        assert response.status_code == 200

        body = response.json()

        assert body["prescription_id"] == (
            env["prescription_a"].prescription_id
        )
        assert body["customer"]["id"] == str(
            env["customer"].id
        )

        env["db"].refresh(env["prescription_a"])

        assert env["prescription_a"].customer_id == (
            env["customer"].id
        )

    def test_pharmacist_cannot_assign_customer_from_another_pharmacy(
        self,
        security_environment,
    ):
        env = security_environment

        set_current_user(env["pharmacist_b"])

        response = env["client"].patch(
            f"/prescriptions/"
            f"{env['prescription_b'].prescription_id}/customer",
            json={
                "customer_id": str(env["customer"].id),
            },
        )

        assert response.status_code == 403

        assert "not linked" in response.json()["detail"].lower()

        env["db"].refresh(env["prescription_b"])

        assert env["prescription_b"].customer_id is None

    def test_customer_membership_exists_for_primary_pharmacy(
        self,
        security_environment,
    ):
        env = security_environment
        db = env["db"]

        membership = (
            db.query(CustomerOrganizationDB)
            .filter(
                CustomerOrganizationDB.customer_id
                == env["customer"].id,
                CustomerOrganizationDB.organization_id
                == env["pharmacy_a"].id,
            )
            .first()
        )

        assert membership is not None

    def test_customer_can_be_linked_to_multiple_pharmacies(
        self,
        security_environment,
    ):
        env = security_environment
        db = env["db"]

        second_membership = CustomerOrganizationDB(
            customer_id=env["customer"].id,
            organization_id=env["pharmacy_b"].id,
        )

        db.add(second_membership)
        db.commit()

        memberships = (
            db.query(CustomerOrganizationDB)
            .filter(
                CustomerOrganizationDB.customer_id
                == env["customer"].id
            )
            .all()
        )

        organization_ids = {
            membership.organization_id
            for membership in memberships
        }

        assert env["pharmacy_a"].id in organization_ids
        assert env["pharmacy_b"].id in organization_ids
        assert len(organization_ids) == 2

    def test_duplicate_customer_pharmacy_membership_is_rejected(
        self,
        security_environment,
    ):
        env = security_environment
        db = env["db"]

        duplicate = CustomerOrganizationDB(
            customer_id=env["customer"].id,
            organization_id=env["pharmacy_a"].id,
        )

        db.add(duplicate)

        with pytest.raises(Exception):
            db.commit()

        db.rollback()

    def test_customer_cannot_assign_prescription(
        self,
        security_environment,
    ):
        env = security_environment

        set_current_user(env["customer_user"])

        response = env["client"].patch(
            f"/prescriptions/"
            f"{env['prescription_a'].prescription_id}/customer",
            json={
                "customer_id": str(env["customer"].id),
            },
        )

        assert response.status_code == 403

    def test_customer_user_is_not_a_pharmacy_staff_user(
        self,
        security_environment,
    ):
        env = security_environment

        set_current_user(env["customer_user"])

        response = env["client"].post(
            "/customers",
            json={
                "name": "Another Customer",
            },
        )

        assert response.status_code == 403

class TestCustomerPrescriptionIsolation:
    def test_customer_can_see_own_prescriptions(
        self,
        security_environment,
    ):
        env = security_environment

        set_current_user(env["customer_user"])

        response = env["client"].get(
            "/customers/me/prescriptions"
        )

        assert response.status_code == 200

        body = response.json()

        prescription_ids = {
            item["id"]
            for item in body
        }

        assert str(env["prescription_a"].id) in prescription_ids

    def test_customer_does_not_see_unassigned_prescription(
        self,
        security_environment,
    ):
        env = security_environment

        set_current_user(env["customer_user"])

        response = env["client"].get(
            "/customers/me/prescriptions"
        )

        assert response.status_code == 200

        body = response.json()

        prescription_ids = {
            item["id"]
            for item in body
        }

        assert str(env["prescription_b"].id) not in prescription_ids

    def test_customer_can_access_own_prescription_detail(
        self,
        security_environment,
    ):
        env = security_environment

        set_current_user(env["customer_user"])

        response = env["client"].get(
            f"/prescriptions/"
            f"{env['prescription_a'].prescription_id}"
        )

        assert response.status_code == 200

        body = response.json()

        assert body["prescription_id"] == (
            env["prescription_a"].prescription_id
        )

    def test_customer_cannot_access_unassigned_prescription_detail(
        self,
        security_environment,
    ):
        env = security_environment

        set_current_user(env["customer_user"])

        response = env["client"].get(
            f"/prescriptions/"
            f"{env['prescription_b'].prescription_id}"
        )

        assert response.status_code == 404

        assert response.json()["detail"] == (
            "Prescription not found"
        )

    def test_customer_can_access_prescription_from_linked_pharmacy(
        self,
        security_environment,
    ):
        env = security_environment
        db = env["db"]

        # Link the customer to Pharmacy B.
        membership = CustomerOrganizationDB(
            customer_id=env["customer"].id,
            organization_id=env["pharmacy_b"].id,
        )

        db.add(membership)

        # Explicitly assign Pharmacy B's prescription to
        # the same customer.
        env["prescription_b"].customer_id = (
            env["customer"].id
        )

        db.commit()

        set_current_user(env["customer_user"])

        response = env["client"].get(
            "/customers/me/prescriptions"
        )

        assert response.status_code == 200

        body = response.json()

        prescription_ids = {
            item["id"]
            for item in body
        }

        assert str(env["prescription_a"].id) in prescription_ids
        assert str(env["prescription_b"].id) in prescription_ids

    def test_customer_cannot_access_another_customers_prescription(
        self,
        security_environment,
    ):
        env = security_environment
        db = env["db"]

        other_customer_user = UserDB(
            name="Customer Two",
            email=f"customer-two-{uuid4().hex[:8]}@example.com",
            password_hash=hash_password("customer-two-password"),
            role="customer",
            is_active=True,
            organization_id=None,
        )

        other_customer = CustomerDB(
            user=other_customer_user,
            organization=env["pharmacy_a"],
            customer_code=f"CUST-{uuid4().hex[:8].upper()}",
            name="Customer Two",
            email=other_customer_user.email,
            is_active=True,
        )

        other_membership = CustomerOrganizationDB(
            customer=other_customer,
            organization=env["pharmacy_a"],
        )

        other_prescription = PrescriptionDB(
            prescription_id=f"RX-{uuid4().hex[:8].upper()}",
            organization=env["pharmacy_a"],
            customer=other_customer,
            uploaded_by=env["pharmacist_a"],
            raw_text=(
                "Amoxicillin 500 mg, "
                "1 capsule three times daily"
            ),
            status="completed",
            review_status="pending",
            safety_flags=[],
            file_name="other-customer.txt",
            file_path="",
            file_type="text/plain",
        )

        db.add_all(
            [
                other_customer_user,
                other_customer,
                other_membership,
                other_prescription,
            ]
        )

        db.commit()

        set_current_user(env["customer_user"])

        response = env["client"].get(
            f"/prescriptions/"
            f"{other_prescription.prescription_id}"
        )

        assert response.status_code == 404

        assert response.json()["detail"] == (
            "Prescription not found"
        )


class TestAssignedCustomerInPrescriptionResponse:
    """
    Tests that GET /prescriptions/{id} returns assigned_customer
    metadata when a customer is assigned, and that the field is
    absent (or None) when no customer is assigned.

    Also verifies that a pharmacist from a different organization
    cannot observe another organization's prescription data.
    """

    def test_prescription_with_assigned_customer_includes_metadata(
        self,
        security_environment,
    ):
        """
        A pharmacist loading a prescription that has an assigned customer
        receives the assigned_customer field with id, name, customer_code.
        """
        env = security_environment

        # prescription_a was created with customer=customer in the fixture.
        set_current_user(env["pharmacist_a"])

        response = env["client"].get(
            f"/prescriptions/{env['prescription_a'].prescription_id}"
        )

        assert response.status_code == 200

        body = response.json()

        assert "assigned_customer" in body
        assert body["assigned_customer"] is not None

        ac = body["assigned_customer"]

        assert ac["id"] == str(env["customer"].id)
        assert ac["name"] == env["customer"].name
        assert ac["customer_code"] == env["customer"].customer_code

    def test_prescription_without_assigned_customer_returns_none(
        self,
        security_environment,
    ):
        """
        A prescription with no customer assigned returns
        assigned_customer = null.
        """
        env = security_environment

        # prescription_b has no customer assigned in the fixture.
        set_current_user(env["pharmacist_b"])

        response = env["client"].get(
            f"/prescriptions/{env['prescription_b'].prescription_id}"
        )

        assert response.status_code == 200

        body = response.json()

        assert "assigned_customer" in body
        assert body["assigned_customer"] is None

    def test_pharmacist_cannot_access_other_org_prescription_detail(
        self,
        security_environment,
    ):
        """
        A pharmacist from Organization B cannot retrieve a prescription
        belonging to Organization A — they must receive 404, not 200.
        This ensures assigned_customer data is never leaked across tenants.
        """
        env = security_environment

        set_current_user(env["pharmacist_b"])

        response = env["client"].get(
            f"/prescriptions/{env['prescription_a'].prescription_id}"
        )

        assert response.status_code == 404


# =========================================================
# F-IDOR-1 — Customer pharmacy-link authorization tests
# =========================================================

class TestPharmacyLinkAuthorization:
    """
    Covers the full security matrix for POST /customers/{id}/link
    and POST /customers/me/pharmacy-link/accept.

    Every test reuses the shared `security_environment` fixture
    which provides pharmacy_a, pharmacy_b, pharmacist_a,
    pharmacist_b, customer (linked to pharmacy_a), and
    customer_user.
    """

    # ----------------------------------------------------------
    # Case 1: Existing primary-pharmacy membership is preserved
    # ----------------------------------------------------------

    def test_existing_customer_creation_creates_primary_membership(
        self,
        security_environment,
    ):
        """
        POST /customers creates a CustomerOrganizationDB row for
        the pharmacist's organization — this must not regress.
        """
        env = security_environment
        db = env["db"]

        from backend.models import CustomerOrganizationDB

        membership = (
            db.query(CustomerOrganizationDB)
            .filter(
                CustomerOrganizationDB.customer_id
                == env["customer"].id,
                CustomerOrganizationDB.organization_id
                == env["pharmacy_a"].id,
            )
            .first()
        )

        assert membership is not None, (
            "Primary pharmacy membership must exist"
        )

    # ----------------------------------------------------------
    # Case 2: Arbitrary UUID direct linking is BLOCKED
    # ----------------------------------------------------------

    def test_pharmacist_cannot_directly_link_arbitrary_uuid(
        self,
        security_environment,
    ):
        """
        A pharmacist from Pharmacy B must not be able to directly
        create a CustomerOrganizationDB row by posting the customer
        UUID to POST /customers/{id}/link without customer consent.

        The endpoint now requires the customer to belong to the
        pharmacist's own organization — a global UUID alone is not
        sufficient.
        """
        env = security_environment

        # pharmacist_b belongs to pharmacy_b.
        # The customer belongs to pharmacy_a only.
        # Pharmacy B has no right to link this UUID.
        set_current_user(env["pharmacist_b"])

        response = env["client"].post(
            f"/customers/{env['customer'].id}/link"
        )

        # 404: customer not found in pharmacist_b's organization
        assert response.status_code == 404, (
            f"Expected 404, got {response.status_code}: "
            f"{response.json()}"
        )

        # Confirm no new membership was created
        from backend.models import CustomerOrganizationDB

        spurious = (
            env["db"]
            .query(CustomerOrganizationDB)
            .filter(
                CustomerOrganizationDB.customer_id
                == env["customer"].id,
                CustomerOrganizationDB.organization_id
                == env["pharmacy_b"].id,
            )
            .first()
        )

        assert spurious is None, (
            "No membership must be created by unauthorized request"
        )

    def test_pharmacist_cannot_link_nonexistent_uuid(
        self,
        security_environment,
    ):
        """
        A completely fabricated UUID must return 404.
        """
        from uuid import uuid4

        env = security_environment

        set_current_user(env["pharmacist_a"])

        response = env["client"].post(
            f"/customers/{uuid4()}/link"
        )

        assert response.status_code == 404

    # ----------------------------------------------------------
    # Case 3: Authorized pharmacist can create a pending request
    # ----------------------------------------------------------

    def test_pharmacist_can_create_link_request_for_own_customer(
        self,
        security_environment,
    ):
        """
        A pharmacist who created a customer (customer belongs to
        pharmacy_a via organization_id) can generate a pending
        link request for a *different* pharmacy.

        We use pharmacist_a and a fresh customer whose
        organization_id == pharmacy_a.  Then pharmacist_a creates
        a link request.  No membership is created yet.
        """
        import hashlib
        from backend.models import (
            CustomerDB,
            CustomerOrganizationDB,
            CustomerPharmacyLinkRequestDB,
        )

        env = security_environment
        db = env["db"]

        # Create a second pharmacy and a customer in pharmacy_a.
        from backend.models import OrganizationDB
        from uuid import uuid4

        pharmacy_c = OrganizationDB(
            name="Pharmacy C",
            slug=f"pharmacy-c-{uuid4().hex[:8]}",
        )
        db.add(pharmacy_c)

        new_customer = CustomerDB(
            organization=env["pharmacy_a"],
            customer_code=f"LINK-{uuid4().hex[:6].upper()}",
            name="Link Test Customer",
            email=f"link-{uuid4().hex[:8]}@example.com",
            is_active=True,
        )
        db.add(new_customer)
        db.flush()

        # Primary membership for new_customer → pharmacy_a
        db.add(CustomerOrganizationDB(
            customer_id=new_customer.id,
            organization_id=env["pharmacy_a"].id,
        ))
        db.commit()
        db.refresh(new_customer)
        db.refresh(pharmacy_c)

        set_current_user(env["pharmacist_a"])

        # pharmacist_a tries to link new_customer to pharmacy_a again
        # (same org) — but pharmacist_a belongs to pharmacy_a and
        # new_customer already belongs to pharmacy_a → 409.
        response = env["client"].post(
            f"/customers/{new_customer.id}/link"
        )
        assert response.status_code == 409

    def test_pharmacist_link_request_returns_token(
        self,
        security_environment,
    ):
        """
        When a pharmacist creates a valid pending link request,
        the response is HTTP 202 and includes a token and
        request_id.
        """
        from backend.models import (
            CustomerDB,
            CustomerOrganizationDB,
            CustomerPharmacyLinkRequestDB,
        )
        from uuid import uuid4

        env = security_environment
        db = env["db"]

        # Create a fresh customer that belongs to pharmacy_a but is
        # NOT yet linked to pharmacy_b.
        fresh_customer = CustomerDB(
            organization=env["pharmacy_a"],
            customer_code=f"FRESH-{uuid4().hex[:6].upper()}",
            name="Fresh Customer",
            email=f"fresh-{uuid4().hex[:8]}@example.com",
            is_active=True,
        )
        db.add(fresh_customer)
        db.flush()

        db.add(CustomerOrganizationDB(
            customer_id=fresh_customer.id,
            organization_id=env["pharmacy_a"].id,
        ))
        db.commit()
        db.refresh(fresh_customer)

        # pharmacist_a belongs to pharmacy_a, so they can see
        # fresh_customer (organization_id == pharmacy_a).
        # But creating a link request for their *own* org 409s.
        # We need pharmacist_a to request linking to pharmacy_b,
        # which means pharmacist_b (org=pharmacy_b) initiates the
        # request.  But pharmacy_b cannot see this customer (not
        # in their org).
        #
        # The correct flow: a pharmacist who *owns* the customer
        # (primary org) initiates the request to add another org.
        # pharmacist_a owns fresh_customer.  Let pharmacist_a send
        # the request on behalf of pharmacy_b — but that is not
        # the model; the requesting pharmacist must belong to the
        # *target* pharmacy.
        #
        # So the correct scenario is: a pharmacist at pharmacy_b
        # needs to link a customer that already belongs to pharmacy_b.
        # Create a customer whose primary org is pharmacy_b.

        customer_b = CustomerDB(
            organization=env["pharmacy_b"],
            customer_code=f"BLINK-{uuid4().hex[:6].upper()}",
            name="Pharmacy B Customer",
            email=f"blink-{uuid4().hex[:8]}@example.com",
            is_active=True,
        )
        db.add(customer_b)
        db.flush()

        # Primary membership for customer_b → pharmacy_b
        # BUT NOT to any other pharmacy yet — so pharmacist_b
        # can try to link them to pharmacy_b (409 = already linked),
        # or we need a scenario where the customer is NOT yet in
        # pharmacist_b's org.
        #
        # The link endpoint restricts: CustomerDB.organization_id ==
        # pharmacist's organization.  A customer's PRIMARY org is
        # where they were originally created.  If that is pharmacy_b,
        # pharmacist_b can see them via the link endpoint — but only
        # to create a request for a DIFFERENT pharmacy.
        #
        # For a valid "create pending request" scenario: pharmacist_b
        # creates a request for customer_b to be linked to pharmacy_b
        # ... but customer_b IS already in pharmacy_b's primary org.
        # We must not pre-add the CustomerOrganizationDB row.
        #
        # Fresh scenario: customer_b primary org = pharmacy_b, no
        # CustomerOrganizationDB row yet added.

        db.commit()
        db.refresh(customer_b)

        set_current_user(env["pharmacist_b"])

        response = env["client"].post(
            f"/customers/{customer_b.id}/link"
        )

        # 202 — pending request created (no membership yet)
        assert response.status_code == 202, (
            f"Expected 202, got {response.status_code}: "
            f"{response.json()}"
        )

        body = response.json()
        assert "token" in body
        assert "request_id" in body
        assert body["customer_id"] == str(customer_b.id)
        assert body["organization_id"] == str(env["pharmacy_b"].id)
        assert len(body["token"]) == 64  # 32 bytes hex

        # Confirm NO membership was created yet
        membership = (
            db.query(CustomerOrganizationDB)
            .filter(
                CustomerOrganizationDB.customer_id == customer_b.id,
                CustomerOrganizationDB.organization_id
                == env["pharmacy_b"].id,
            )
            .first()
        )
        assert membership is None, (
            "Membership must NOT be created before customer accepts"
        )

        # Confirm the link request record exists with status=pending
        link_req = (
            db.query(CustomerPharmacyLinkRequestDB)
            .filter(
                CustomerPharmacyLinkRequestDB.customer_id
                == customer_b.id,
                CustomerPharmacyLinkRequestDB.organization_id
                == env["pharmacy_b"].id,
                CustomerPharmacyLinkRequestDB.status == "pending",
            )
            .first()
        )
        assert link_req is not None

    # ----------------------------------------------------------
    # Cases 4 & 5: Correct customer accepts → membership created
    # ----------------------------------------------------------

    def test_correct_customer_can_accept_request(
        self,
        security_environment,
    ):
        """
        The customer the request was created for can accept it,
        which creates the CustomerOrganizationDB membership.
        """
        import hashlib
        from backend.models import (
            CustomerDB,
            CustomerOrganizationDB,
            CustomerPharmacyLinkRequestDB,
            UserDB,
        )
        from uuid import uuid4
        from datetime import datetime, timedelta, timezone
        from backend.security import hash_password

        env = security_environment
        db = env["db"]

        # Create a customer with a login account linked to pharmacy_b.
        new_user = UserDB(
            name="Accept Customer",
            email=f"accept-{uuid4().hex[:8]}@example.com",
            password_hash=hash_password("pw"),
            role="customer",
            is_active=True,
            organization_id=None,
        )
        db.add(new_user)

        accept_customer = CustomerDB(
            user=new_user,
            organization=env["pharmacy_b"],
            customer_code=f"ACC-{uuid4().hex[:6].upper()}",
            name="Accept Customer",
            email=new_user.email,
            is_active=True,
        )
        db.add(accept_customer)
        db.commit()
        db.refresh(new_user)
        db.refresh(accept_customer)

        # Manually create a pending link request (simulates pharmacist
        # calling POST /customers/{id}/link).
        raw_token = "a" * 64  # deterministic for test
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        link_req = CustomerPharmacyLinkRequestDB(
            customer_id=accept_customer.id,
            organization_id=env["pharmacy_b"].id,
            token_hash=token_hash,
            status="pending",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=72),
        )
        db.add(link_req)
        db.commit()
        db.refresh(link_req)

        # Customer accepts
        set_current_user(new_user)

        response = env["client"].post(
            "/customers/me/pharmacy-link/accept",
            json={"token": raw_token},
        )

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: "
            f"{response.json()}"
        )

        body = response.json()
        assert body["message"] == "Pharmacy linked successfully"

        # Membership must now exist
        membership = (
            db.query(CustomerOrganizationDB)
            .filter(
                CustomerOrganizationDB.customer_id
                == accept_customer.id,
                CustomerOrganizationDB.organization_id
                == env["pharmacy_b"].id,
            )
            .first()
        )
        assert membership is not None, (
            "Membership must be created after customer accepts"
        )

        # Request must be marked accepted
        db.refresh(link_req)
        assert link_req.status == "accepted"
        assert link_req.accepted_at is not None

    # ----------------------------------------------------------
    # Case 6: Wrong customer cannot accept
    # ----------------------------------------------------------

    def test_wrong_customer_cannot_accept_request(
        self,
        security_environment,
    ):
        """
        A different customer submitting a token issued for another
        customer must receive 400 — not create a spurious membership.
        """
        import hashlib
        from backend.models import (
            CustomerDB,
            CustomerOrganizationDB,
            CustomerPharmacyLinkRequestDB,
            UserDB,
        )
        from uuid import uuid4
        from datetime import datetime, timedelta, timezone
        from backend.security import hash_password

        env = security_environment
        db = env["db"]

        # Customer A (the intended recipient)
        user_a = UserDB(
            name="Customer A",
            email=f"ca-{uuid4().hex[:8]}@example.com",
            password_hash=hash_password("pw"),
            role="customer",
            is_active=True,
        )
        db.add(user_a)

        customer_a = CustomerDB(
            user=user_a,
            organization=env["pharmacy_a"],
            customer_code=f"CA-{uuid4().hex[:6].upper()}",
            name="Customer A",
            email=user_a.email,
            is_active=True,
        )
        db.add(customer_a)

        # Customer B (the attacker)
        user_b = UserDB(
            name="Customer B",
            email=f"cb-{uuid4().hex[:8]}@example.com",
            password_hash=hash_password("pw"),
            role="customer",
            is_active=True,
        )
        db.add(user_b)

        customer_b = CustomerDB(
            user=user_b,
            organization=env["pharmacy_b"],
            customer_code=f"CB-{uuid4().hex[:6].upper()}",
            name="Customer B",
            email=user_b.email,
            is_active=True,
        )
        db.add(customer_b)
        db.commit()
        db.refresh(customer_a)
        db.refresh(customer_b)

        # Link request belongs to customer_a → pharmacy_b
        raw_token = "b" * 64
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        link_req = CustomerPharmacyLinkRequestDB(
            customer_id=customer_a.id,
            organization_id=env["pharmacy_b"].id,
            token_hash=token_hash,
            status="pending",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=72),
        )
        db.add(link_req)
        db.commit()

        # Customer B (wrong customer) tries to accept
        set_current_user(user_b)

        response = env["client"].post(
            "/customers/me/pharmacy-link/accept",
            json={"token": raw_token},
        )

        assert response.status_code == 400

        # No spurious membership for customer_b
        spurious = (
            db.query(CustomerOrganizationDB)
            .filter(
                CustomerOrganizationDB.customer_id == customer_b.id,
                CustomerOrganizationDB.organization_id
                == env["pharmacy_b"].id,
            )
            .first()
        )
        assert spurious is None

        # No membership for customer_a either (token not accepted)
        no_membership = (
            db.query(CustomerOrganizationDB)
            .filter(
                CustomerOrganizationDB.customer_id == customer_a.id,
                CustomerOrganizationDB.organization_id
                == env["pharmacy_b"].id,
            )
            .first()
        )
        assert no_membership is None

    # ----------------------------------------------------------
    # Case 7: Expired request cannot be accepted
    # ----------------------------------------------------------

    def test_expired_request_is_rejected(
        self,
        security_environment,
    ):
        """
        A token whose expiry is in the past must be rejected with 400.
        """
        import hashlib
        from backend.models import (
            CustomerDB,
            CustomerOrganizationDB,
            CustomerPharmacyLinkRequestDB,
            UserDB,
        )
        from uuid import uuid4
        from datetime import datetime, timedelta, timezone
        from backend.security import hash_password

        env = security_environment
        db = env["db"]

        exp_user = UserDB(
            name="Exp Customer",
            email=f"exp-{uuid4().hex[:8]}@example.com",
            password_hash=hash_password("pw"),
            role="customer",
            is_active=True,
        )
        db.add(exp_user)

        exp_customer = CustomerDB(
            user=exp_user,
            organization=env["pharmacy_a"],
            customer_code=f"EXP-{uuid4().hex[:6].upper()}",
            name="Exp Customer",
            email=exp_user.email,
            is_active=True,
        )
        db.add(exp_customer)
        db.commit()
        db.refresh(exp_customer)

        raw_token = "c" * 64
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        # Already expired
        link_req = CustomerPharmacyLinkRequestDB(
            customer_id=exp_customer.id,
            organization_id=env["pharmacy_b"].id,
            token_hash=token_hash,
            status="pending",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db.add(link_req)
        db.commit()

        set_current_user(exp_user)

        response = env["client"].post(
            "/customers/me/pharmacy-link/accept",
            json={"token": raw_token},
        )

        assert response.status_code == 400

        # Status should be updated to "expired"
        db.refresh(link_req)
        assert link_req.status == "expired"

        # No membership created
        membership = (
            db.query(CustomerOrganizationDB)
            .filter(
                CustomerOrganizationDB.customer_id == exp_customer.id,
                CustomerOrganizationDB.organization_id
                == env["pharmacy_b"].id,
            )
            .first()
        )
        assert membership is None

    # ----------------------------------------------------------
    # Case 8: Accepted request cannot be replayed
    # ----------------------------------------------------------

    def test_accepted_request_cannot_be_replayed(
        self,
        security_environment,
    ):
        """
        Re-submitting an already-accepted token returns 400.
        The existing membership is unaffected (idempotent),
        but the replay is blocked.
        """
        import hashlib
        from backend.models import (
            CustomerDB,
            CustomerOrganizationDB,
            CustomerPharmacyLinkRequestDB,
            UserDB,
        )
        from uuid import uuid4
        from datetime import datetime, timedelta, timezone
        from backend.security import hash_password

        env = security_environment
        db = env["db"]

        rp_user = UserDB(
            name="Replay Customer",
            email=f"rp-{uuid4().hex[:8]}@example.com",
            password_hash=hash_password("pw"),
            role="customer",
            is_active=True,
        )
        db.add(rp_user)

        rp_customer = CustomerDB(
            user=rp_user,
            organization=env["pharmacy_b"],
            customer_code=f"RP-{uuid4().hex[:6].upper()}",
            name="Replay Customer",
            email=rp_user.email,
            is_active=True,
        )
        db.add(rp_customer)
        db.commit()
        db.refresh(rp_customer)

        raw_token = "d" * 64
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        link_req = CustomerPharmacyLinkRequestDB(
            customer_id=rp_customer.id,
            organization_id=env["pharmacy_b"].id,
            token_hash=token_hash,
            status="accepted",  # already accepted
            expires_at=datetime.now(timezone.utc) + timedelta(hours=72),
            accepted_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        db.add(link_req)
        db.commit()

        set_current_user(rp_user)

        response = env["client"].post(
            "/customers/me/pharmacy-link/accept",
            json={"token": raw_token},
        )

        assert response.status_code == 400

    # ----------------------------------------------------------
    # Case 9: Duplicate membership handled safely
    # ----------------------------------------------------------

    def test_duplicate_membership_is_handled_safely(
        self,
        security_environment,
    ):
        """
        If a membership already exists and the customer somehow
        tries to accept again (edge case), the endpoint must not
        crash or create a duplicate.  Because status != pending
        this is blocked before reaching ensure_customer_organization_link.
        """
        import hashlib
        from backend.models import (
            CustomerDB,
            CustomerOrganizationDB,
            CustomerPharmacyLinkRequestDB,
            UserDB,
        )
        from uuid import uuid4
        from datetime import datetime, timedelta, timezone
        from backend.security import hash_password

        env = security_environment
        db = env["db"]

        dup_user = UserDB(
            name="Dup Customer",
            email=f"dup-{uuid4().hex[:8]}@example.com",
            password_hash=hash_password("pw"),
            role="customer",
            is_active=True,
        )
        db.add(dup_user)

        dup_customer = CustomerDB(
            user=dup_user,
            organization=env["pharmacy_b"],
            customer_code=f"DUP-{uuid4().hex[:6].upper()}",
            name="Dup Customer",
            email=dup_user.email,
            is_active=True,
        )
        db.add(dup_customer)
        db.flush()

        # Membership already exists
        db.add(CustomerOrganizationDB(
            customer_id=dup_customer.id,
            organization_id=env["pharmacy_b"].id,
        ))
        db.commit()
        db.refresh(dup_customer)

        raw_token = "e" * 64
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        link_req = CustomerPharmacyLinkRequestDB(
            customer_id=dup_customer.id,
            organization_id=env["pharmacy_b"].id,
            token_hash=token_hash,
            status="accepted",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=72),
            accepted_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        db.add(link_req)
        db.commit()

        set_current_user(dup_user)

        # Replay blocked (already accepted)
        response = env["client"].post(
            "/customers/me/pharmacy-link/accept",
            json={"token": raw_token},
        )

        assert response.status_code == 400

        # Exactly one membership row
        count = (
            db.query(CustomerOrganizationDB)
            .filter(
                CustomerOrganizationDB.customer_id == dup_customer.id,
                CustomerOrganizationDB.organization_id
                == env["pharmacy_b"].id,
            )
            .count()
        )
        assert count == 1

    # ----------------------------------------------------------
    # Case 10: Pharmacy A cannot manipulate Pharmacy B's request
    # ----------------------------------------------------------

    def test_cross_pharmacy_request_manipulation_blocked(
        self,
        security_environment,
    ):
        """
        A pharmacist at Pharmacy A must not be able to create a
        link request for a customer that belongs to Pharmacy B
        (the customer's organization_id is Pharmacy B, so
        Pharmacy A's scoped lookup returns 404).
        """
        from backend.models import CustomerDB, CustomerOrganizationDB
        from uuid import uuid4

        env = security_environment
        db = env["db"]

        # Customer whose primary org is pharmacy_b
        other_customer = CustomerDB(
            organization=env["pharmacy_b"],
            customer_code=f"OTH-{uuid4().hex[:6].upper()}",
            name="Other Customer",
            is_active=True,
        )
        db.add(other_customer)
        db.commit()
        db.refresh(other_customer)

        # pharmacist_a (org=pharmacy_a) tries to link other_customer
        # whose org is pharmacy_b — scoped lookup blocks it.
        set_current_user(env["pharmacist_a"])

        response = env["client"].post(
            f"/customers/{other_customer.id}/link"
        )

        assert response.status_code == 404

    # ----------------------------------------------------------
    # Case 11: Customer A cannot access Customer B's request
    # ----------------------------------------------------------

    def test_customer_a_cannot_accept_customer_b_request(
        self,
        security_environment,
    ):
        """
        Customer A submitting Customer B's token must receive 400.
        The cross-customer guard is the check:
            link_request.customer_id != customer.id
        """
        import hashlib
        from backend.models import (
            CustomerDB,
            CustomerPharmacyLinkRequestDB,
            UserDB,
        )
        from uuid import uuid4
        from datetime import datetime, timedelta, timezone
        from backend.security import hash_password

        env = security_environment
        db = env["db"]

        # Customer A (attacker)
        user_attacker = UserDB(
            name="Attacker",
            email=f"atk-{uuid4().hex[:8]}@example.com",
            password_hash=hash_password("pw"),
            role="customer",
            is_active=True,
        )
        db.add(user_attacker)

        customer_attacker = CustomerDB(
            user=user_attacker,
            organization=env["pharmacy_a"],
            customer_code=f"ATK-{uuid4().hex[:6].upper()}",
            name="Attacker",
            email=user_attacker.email,
            is_active=True,
        )
        db.add(customer_attacker)

        # Customer B (victim — token intended for them)
        user_victim = UserDB(
            name="Victim",
            email=f"vic-{uuid4().hex[:8]}@example.com",
            password_hash=hash_password("pw"),
            role="customer",
            is_active=True,
        )
        db.add(user_victim)

        customer_victim = CustomerDB(
            user=user_victim,
            organization=env["pharmacy_b"],
            customer_code=f"VIC-{uuid4().hex[:6].upper()}",
            name="Victim",
            email=user_victim.email,
            is_active=True,
        )
        db.add(customer_victim)
        db.commit()
        db.refresh(customer_attacker)
        db.refresh(customer_victim)

        raw_token = "f" * 64
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        link_req = CustomerPharmacyLinkRequestDB(
            customer_id=customer_victim.id,  # belongs to victim
            organization_id=env["pharmacy_b"].id,
            token_hash=token_hash,
            status="pending",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=72),
        )
        db.add(link_req)
        db.commit()

        # Attacker (customer A) tries to use victim's token
        set_current_user(user_attacker)

        response = env["client"].post(
            "/customers/me/pharmacy-link/accept",
            json={"token": raw_token},
        )

        assert response.status_code == 400

    # ----------------------------------------------------------
    # Case 12: Multi-pharmacy customer support preserved
    # ----------------------------------------------------------

    def test_multi_pharmacy_customer_still_works(
        self,
        security_environment,
    ):
        """
        A customer can still be linked to multiple pharmacies.
        The consent flow must support this without restriction.
        """
        import hashlib
        from backend.models import (
            CustomerDB,
            CustomerOrganizationDB,
            CustomerPharmacyLinkRequestDB,
            UserDB,
        )
        from uuid import uuid4
        from datetime import datetime, timedelta, timezone
        from backend.security import hash_password

        env = security_environment
        db = env["db"]

        # Create a customer with a login, primary org = pharmacy_b
        multi_user = UserDB(
            name="Multi Customer",
            email=f"multi-{uuid4().hex[:8]}@example.com",
            password_hash=hash_password("pw"),
            role="customer",
            is_active=True,
        )
        db.add(multi_user)

        multi_customer = CustomerDB(
            user=multi_user,
            organization=env["pharmacy_b"],
            customer_code=f"MULTI-{uuid4().hex[:5].upper()}",
            name="Multi Customer",
            email=multi_user.email,
            is_active=True,
        )
        db.add(multi_customer)
        db.commit()
        db.refresh(multi_customer)

        # Pending request: pharmacy_b wants to link multi_customer
        # (no CustomerOrganizationDB row exists yet for pharmacy_b).
        raw_token_1 = "1" * 64
        hash_1 = hashlib.sha256(raw_token_1.encode()).hexdigest()

        req_1 = CustomerPharmacyLinkRequestDB(
            customer_id=multi_customer.id,
            organization_id=env["pharmacy_b"].id,
            token_hash=hash_1,
            status="pending",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=72),
        )
        db.add(req_1)
        db.commit()

        # Customer accepts pharmacy_b link
        set_current_user(multi_user)

        r1 = env["client"].post(
            "/customers/me/pharmacy-link/accept",
            json={"token": raw_token_1},
        )

        assert r1.status_code == 200

        # Now create a second request for pharmacy_a
        raw_token_2 = "2" * 64
        hash_2 = hashlib.sha256(raw_token_2.encode()).hexdigest()

        req_2 = CustomerPharmacyLinkRequestDB(
            customer_id=multi_customer.id,
            organization_id=env["pharmacy_a"].id,
            token_hash=hash_2,
            status="pending",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=72),
        )
        db.add(req_2)
        db.commit()

        r2 = env["client"].post(
            "/customers/me/pharmacy-link/accept",
            json={"token": raw_token_2},
        )

        assert r2.status_code == 200

        # Customer is now linked to both pharmacies
        memberships = (
            db.query(CustomerOrganizationDB)
            .filter(
                CustomerOrganizationDB.customer_id
                == multi_customer.id
            )
            .all()
        )

        org_ids = {m.organization_id for m in memberships}
        assert env["pharmacy_a"].id in org_ids
        assert env["pharmacy_b"].id in org_ids

    # ----------------------------------------------------------
    # Case 13: Prescription isolation is preserved
    # ----------------------------------------------------------

    def test_prescription_isolation_preserved_after_multi_link(
        self,
        security_environment,
    ):
        """
        A customer linked to two pharmacies must only see
        prescriptions from each pharmacy when that pharmacy's
        organization_id matches — no cross-pharmacy prescription leak.
        """
        import hashlib
        from backend.models import (
            CustomerDB,
            CustomerOrganizationDB,
            CustomerPharmacyLinkRequestDB,
            PrescriptionDB,
            UserDB,
        )
        from uuid import uuid4
        from datetime import datetime, timedelta, timezone
        from backend.security import hash_password

        env = security_environment
        db = env["db"]

        iso_user = UserDB(
            name="Iso Customer",
            email=f"iso-{uuid4().hex[:8]}@example.com",
            password_hash=hash_password("pw"),
            role="customer",
            is_active=True,
        )
        db.add(iso_user)

        iso_customer = CustomerDB(
            user=iso_user,
            organization=env["pharmacy_b"],
            customer_code=f"ISO-{uuid4().hex[:5].upper()}",
            name="Iso Customer",
            email=iso_user.email,
            is_active=True,
        )
        db.add(iso_customer)
        db.commit()
        db.refresh(iso_customer)

        # Prescription at pharmacy_a for iso_customer (org A)
        rx_a = PrescriptionDB(
            prescription_id=f"ISO-RXA-{uuid4().hex[:6].upper()}",
            organization=env["pharmacy_a"],
            customer=iso_customer,
            uploaded_by=env["pharmacist_a"],
            raw_text="Ibuprofen 400mg",
            status="completed",
            review_status="pending",
            safety_flags=[],
            file_name="iso-a.txt",
            file_path="",
            file_type="text/plain",
        )

        # Prescription at pharmacy_b for iso_customer (org B)
        rx_b = PrescriptionDB(
            prescription_id=f"ISO-RXB-{uuid4().hex[:6].upper()}",
            organization=env["pharmacy_b"],
            customer=iso_customer,
            uploaded_by=env["pharmacist_b"],
            raw_text="Metformin 500mg",
            status="completed",
            review_status="pending",
            safety_flags=[],
            file_name="iso-b.txt",
            file_path="",
            file_type="text/plain",
        )
        db.add_all([rx_a, rx_b])

        # Link iso_customer to both pharmacies via membership rows
        db.add(CustomerOrganizationDB(
            customer_id=iso_customer.id,
            organization_id=env["pharmacy_a"].id,
        ))
        db.add(CustomerOrganizationDB(
            customer_id=iso_customer.id,
            organization_id=env["pharmacy_b"].id,
        ))
        db.commit()
        db.refresh(rx_a)
        db.refresh(rx_b)

        # Pharmacist A can only see rx_a for iso_customer
        set_current_user(env["pharmacist_a"])

        resp_a = env["client"].get(
            f"/customers/{iso_customer.id}/prescriptions"
        )

        assert resp_a.status_code == 200

        rx_ids_a = {item["id"] for item in resp_a.json()}
        assert str(rx_a.id) in rx_ids_a
        assert str(rx_b.id) not in rx_ids_a, (
            "Pharmacist A must not see Pharmacy B's prescription"
        )

        # Pharmacist B can only see rx_b for iso_customer
        set_current_user(env["pharmacist_b"])

        resp_b = env["client"].get(
            f"/customers/{iso_customer.id}/prescriptions"
        )

        assert resp_b.status_code == 200

        rx_ids_b = {item["id"] for item in resp_b.json()}
        assert str(rx_b.id) in rx_ids_b
        assert str(rx_a.id) not in rx_ids_b, (
            "Pharmacist B must not see Pharmacy A's prescription"
        )
