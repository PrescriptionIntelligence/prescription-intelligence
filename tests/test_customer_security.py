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
