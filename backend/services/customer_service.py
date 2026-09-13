from __future__ import annotations

import secrets

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.models import (
    CustomerDB,
    CustomerOrganizationDB,
    OrganizationDB,
    UserDB,
)


def generate_customer_code(
    name: str,
    db: Session,
) -> str:
    """
    Generate a unique customer code.

    Example:
        JOHN-4821
    """

    prefix = "".join(
        character
        for character in name.upper()
        if character.isalnum()
    )[:8]

    if not prefix:
        prefix = "CUSTOMER"

    for _ in range(20):
        code = f"{prefix}-{secrets.randbelow(9000) + 1000}"

        existing = (
            db.query(CustomerDB)
            .filter(
                CustomerDB.customer_code == code
            )
            .first()
        )

        if existing is None:
            return code

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unable to generate a unique customer code",
    )


def get_customer_by_user(
    user_id,
    db: Session,
) -> CustomerDB | None:
    """
    Find a customer profile using the global UserDB account.
    """

    return (
        db.query(CustomerDB)
        .filter(
            CustomerDB.user_id == user_id
        )
        .first()
    )


def get_or_create_customer_profile(
    user: UserDB,
    db: Session,
    organization: OrganizationDB | None = None,
    phone: str | None = None,
) -> CustomerDB:
    """
    Get the customer's global profile.

    If the profile does not exist, create it.

    The current database still requires CustomerDB.organization_id,
    so an organization must be supplied when creating a profile.
    """

    if user.role != "customer":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not a customer",
        )

    customer = get_customer_by_user(
        user.id,
        db,
    )

    if customer:
        if phone and not customer.phone:
            customer.phone = phone

        return customer

    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "A pharmacy organization is required when "
                "creating the customer profile"
            ),
        )

    customer = CustomerDB(
        user_id=user.id,
        organization_id=organization.id,
        name=user.name,
        email=user.email,
        phone=phone,
        customer_code=generate_customer_code(
            user.name,
            db,
        ),
    )

    db.add(customer)
    db.flush()

    return customer


def link_customer_to_organization(
    customer: CustomerDB,
    organization: OrganizationDB,
    db: Session,
) -> CustomerOrganizationDB:
    """
    Link a customer to a pharmacy organization.

    Duplicate links are safely ignored.
    """

    existing = (
        db.query(CustomerOrganizationDB)
        .filter(
            CustomerOrganizationDB.customer_id
            == customer.id,
            CustomerOrganizationDB.organization_id
            == organization.id,
        )
        .first()
    )

    if existing:
        return existing

    membership = CustomerOrganizationDB(
        customer_id=customer.id,
        organization_id=organization.id,
    )

    db.add(membership)
    db.flush()

    return membership


def ensure_customer_organization_link(
    customer: CustomerDB,
    organization: OrganizationDB,
    db: Session,
) -> CustomerOrganizationDB:
    """
    Ensure that a customer belongs to a pharmacy.

    This is the preferred helper for prescription creation.
    """

    return link_customer_to_organization(
        customer=customer,
        organization=organization,
        db=db,
    )


def customer_belongs_to_organization(
    customer_id,
    organization_id,
    db: Session,
) -> bool:
    """
    Check whether a customer is associated with a pharmacy.
    """

    return (
        db.query(CustomerOrganizationDB)
        .filter(
            CustomerOrganizationDB.customer_id
            == customer_id,
            CustomerOrganizationDB.organization_id
            == organization_id,
        )
        .first()
        is not None
    )


def get_customer_organizations(
    customer_id,
    db: Session,
) -> list[OrganizationDB]:
    """
    Return all pharmacies associated with a customer.
    """

    return (
        db.query(OrganizationDB)
        .join(
            CustomerOrganizationDB,
            CustomerOrganizationDB.organization_id
            == OrganizationDB.id,
        )
        .filter(
            CustomerOrganizationDB.customer_id
            == customer_id
        )
        .order_by(
            OrganizationDB.name.asc()
        )
        .all()
    )


def get_customer_organization_ids(
    customer_id,
    db: Session,
) -> list:
    """
    Return all organization IDs associated with a customer.
    """

    rows = (
        db.query(
            CustomerOrganizationDB.organization_id
        )
        .filter(
            CustomerOrganizationDB.customer_id
            == customer_id
        )
        .all()
    )

    return [
        row[0]
        for row in rows
    ]