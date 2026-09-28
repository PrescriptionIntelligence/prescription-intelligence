"""P7.12-D: add tokens_valid_after to users and revoked_access_tokens table

Revision ID: d1e2f3a4b5c6
Revises: c4d5e6f7a8b9
Create Date: 2026-10-01 00:00:00.000000

Changes:
    1. users.tokens_valid_after  TIMESTAMPTZ NULL
       Global revocation fence used by password reset to invalidate
       all JWTs issued before the reset timestamp.

    2. revoked_access_tokens table
       Per-token denylist used by logout to revoke a single JWT
       without invalidating other sessions for the same user.
       Only the jti (JWT ID) is stored — never the raw token.

Both DDL statements use IF NOT EXISTS / ADD COLUMN IF NOT EXISTS so
the migration is safe to re-run against a database that may already
have the column/table from a manual repair.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. users.tokens_valid_after
    #
    # NULL for all existing rows (no fence active by default).
    # ------------------------------------------------------------------
    op.execute("""
        ALTER TABLE users
            ADD COLUMN IF NOT EXISTS tokens_valid_after TIMESTAMPTZ NULL
    """)

    # ------------------------------------------------------------------
    # 2. revoked_access_tokens
    #
    # Stores the jti of revoked JWTs until their natural expiry.
    # The raw JWT is never stored.
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS revoked_access_tokens (
            id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            jti         VARCHAR(36) NOT NULL,
            user_id     UUID        NOT NULL
                                    REFERENCES users(id)
                                    ON DELETE CASCADE,
            expires_at  TIMESTAMPTZ NOT NULL,
            revoked_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS
            ix_revoked_access_tokens_jti
            ON revoked_access_tokens(jti)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS
            ix_revoked_access_tokens_user_id
            ON revoked_access_tokens(user_id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS
            ix_revoked_access_tokens_expires_at
            ON revoked_access_tokens(expires_at)
    """)


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS ix_revoked_access_tokens_expires_at"
    )
    op.execute(
        "DROP INDEX IF EXISTS ix_revoked_access_tokens_user_id"
    )
    op.execute(
        "DROP INDEX IF EXISTS ix_revoked_access_tokens_jti"
    )
    op.execute(
        "DROP TABLE IF EXISTS revoked_access_tokens"
    )
    op.execute("""
        ALTER TABLE users
            DROP COLUMN IF EXISTS tokens_valid_after
    """)
