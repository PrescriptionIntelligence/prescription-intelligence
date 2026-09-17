"""add customer_organizations table

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-09-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Create the customer_organizations join table.

    Supports the many-to-many relationship between customers
    and pharmacy organizations.  A customer may be associated
    with multiple pharmacies simultaneously.

    Uses IF NOT EXISTS so the migration is safe to run against
    a database that already has the table (e.g. from a manual
    schema repair).
    """
    op.execute("""
        CREATE TABLE IF NOT EXISTS customer_organizations (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            customer_id     UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
            organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_customer_organization
                UNIQUE (customer_id, organization_id)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_customer_organizations_customer_id
            ON customer_organizations(customer_id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_customer_organizations_organization_id
            ON customer_organizations(organization_id)
    """)


def downgrade() -> None:
    """Drop the customer_organizations table."""
    op.execute(
        "DROP INDEX IF EXISTS ix_customer_organizations_organization_id"
    )
    op.execute(
        "DROP INDEX IF EXISTS ix_customer_organizations_customer_id"
    )
    op.execute(
        "DROP TABLE IF EXISTS customer_organizations"
    )
