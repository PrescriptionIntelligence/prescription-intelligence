"""add password_reset_tokens table

Revision ID: f1a2b3c4d5e6
Revises: 8e5bed12ba6c
Create Date: 2026-09-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "8e5bed12ba6c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Create the password_reset_tokens table.

    Only the SHA-256 hash of each token is stored.
    The raw token is sent to the user by email and never
    persisted to the database.
    """
    op.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash  VARCHAR(64) NOT NULL UNIQUE,
            expires_at  TIMESTAMPTZ NOT NULL,
            used_at     TIMESTAMPTZ,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_password_reset_tokens_user_id
            ON password_reset_tokens(user_id)
    """)

    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ix_password_reset_tokens_token_hash
            ON password_reset_tokens(token_hash)
    """)


def downgrade() -> None:
    """Drop the password_reset_tokens table."""
    op.execute(
        "DROP INDEX IF EXISTS ix_password_reset_tokens_token_hash"
    )
    op.execute(
        "DROP INDEX IF EXISTS ix_password_reset_tokens_user_id"
    )
    op.execute(
        "DROP TABLE IF EXISTS password_reset_tokens"
    )
