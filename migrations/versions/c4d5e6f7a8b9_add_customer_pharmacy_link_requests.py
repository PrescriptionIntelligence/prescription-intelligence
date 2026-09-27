"""add customer_pharmacy_link_requests table

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-09-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, Sequence[str], None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Create the customer_pharmacy_link_requests table.

    Stores pending customer-consent requests for a pharmacy to link
    a global CustomerDB account to their organization.

    The two-phase workflow:
        1. Pharmacist calls POST /customers/{id}/link.
           A pending row is inserted here; no membership is created yet.
        2. Customer calls POST /customers/me/pharmacy-link/accept
           with the raw token.
        3. The backend hashes the token, looks up this row, verifies
           ownership and expiry, creates CustomerOrganizationDB, and
           marks the row accepted.

    Security properties encoded in the schema:
        - token_hash is UNIQUE: each token can only exist once globally.
        - ON DELETE CASCADE on both FKs: rows are cleaned up automatically
          when a customer or organization is deleted.
        - No composite UNIQUE on (customer_id, organization_id): multiple
          pending requests for the same pair are intentionally permitted
          (e.g. pharmacist regenerates a token after the previous one expired).

    Uses IF NOT EXISTS so re-running against a database that already has
    the table (e.g. from a manual python -m backend.migrate repair) is safe.
    """
    op.execute("""
        CREATE TABLE IF NOT EXISTS customer_pharmacy_link_requests (
            id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            customer_id      UUID        NOT NULL
                                         REFERENCES customers(id)
                                         ON DELETE CASCADE,
            organization_id  UUID        NOT NULL
                                         REFERENCES organizations(id)
                                         ON DELETE CASCADE,
            token_hash       VARCHAR(64) NOT NULL UNIQUE,
            status           VARCHAR(16) NOT NULL DEFAULT 'pending',
            expires_at       TIMESTAMPTZ NOT NULL,
            accepted_at      TIMESTAMPTZ,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS
            ix_customer_pharmacy_link_requests_customer_id
            ON customer_pharmacy_link_requests(customer_id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS
            ix_customer_pharmacy_link_requests_organization_id
            ON customer_pharmacy_link_requests(organization_id)
    """)

    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS
            ix_customer_pharmacy_link_requests_token_hash
            ON customer_pharmacy_link_requests(token_hash)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS
            ix_customer_pharmacy_link_requests_status
            ON customer_pharmacy_link_requests(status)
    """)


def downgrade() -> None:
    """Drop the customer_pharmacy_link_requests table and its indexes."""
    op.execute(
        "DROP INDEX IF EXISTS "
        "ix_customer_pharmacy_link_requests_status"
    )
    op.execute(
        "DROP INDEX IF EXISTS "
        "ix_customer_pharmacy_link_requests_token_hash"
    )
    op.execute(
        "DROP INDEX IF EXISTS "
        "ix_customer_pharmacy_link_requests_organization_id"
    )
    op.execute(
        "DROP INDEX IF EXISTS "
        "ix_customer_pharmacy_link_requests_customer_id"
    )
    op.execute(
        "DROP TABLE IF EXISTS customer_pharmacy_link_requests"
    )
