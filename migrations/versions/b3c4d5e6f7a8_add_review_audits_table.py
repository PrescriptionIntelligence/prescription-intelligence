"""add review_audits table

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-09-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, Sequence[str], None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Create the review_audits table.

    Each row is an immutable record of one pharmacist review action.
    Used by the review workflow, PDF report generator, and admin audit log.

    Uses IF NOT EXISTS so running against a database that already has
    the table (e.g. from a manual schema repair) is safe.
    """
    op.execute("""
        CREATE TABLE IF NOT EXISTS review_audits (
            id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            prescription_id  UUID        NOT NULL REFERENCES prescriptions(id),
            reviewer_id      UUID        NOT NULL REFERENCES users(id),
            action           VARCHAR(30) NOT NULL,
            previous_status  VARCHAR(30) NOT NULL,
            new_status       VARCHAR(30) NOT NULL,
            finding_type     VARCHAR(100),
            finding_data     JSON,
            note             TEXT,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_review_audits_prescription_id
            ON review_audits(prescription_id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_review_audits_reviewer_id
            ON review_audits(reviewer_id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_review_audits_action
            ON review_audits(action)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_review_audits_finding_type
            ON review_audits(finding_type)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_review_audits_created_at
            ON review_audits(created_at)
    """)


def downgrade() -> None:
    """Drop the review_audits table and its indexes."""
    op.execute("DROP INDEX IF EXISTS ix_review_audits_created_at")
    op.execute("DROP INDEX IF EXISTS ix_review_audits_finding_type")
    op.execute("DROP INDEX IF EXISTS ix_review_audits_action")
    op.execute("DROP INDEX IF EXISTS ix_review_audits_reviewer_id")
    op.execute("DROP INDEX IF EXISTS ix_review_audits_prescription_id")
    op.execute("DROP TABLE IF EXISTS review_audits")
