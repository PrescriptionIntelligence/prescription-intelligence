"""add email verification to users

Revision ID: 48bd7450eca0
Revises: e1a2b3c4d5e6
Create Date: 2026-09-14
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "48bd7450eca0"
down_revision = "e1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -----------------------------------------------------
    # Add as nullable first so existing accounts survive.
    # -----------------------------------------------------

    op.add_column(
        "users",
        sa.Column(
            "email_verified",
            sa.Boolean(),
            nullable=True,
        ),
    )

    # -----------------------------------------------------
    # Existing accounts were created before mandatory
    # email verification existed.
    #
    # Treat them as already verified so we do not lock
    # existing users out of the application.
    # -----------------------------------------------------

    op.execute(
        sa.text(
            """
            UPDATE users
            SET email_verified = TRUE
            WHERE email_verified IS NULL
            """
        )
    )

    # -----------------------------------------------------
    # New accounts must explicitly have a boolean value.
    # -----------------------------------------------------

    op.alter_column(
        "users",
        "email_verified",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.false(),
    )

    # -----------------------------------------------------
    # Verification token storage.
    # -----------------------------------------------------

    op.add_column(
        "users",
        sa.Column(
            "email_verification_token_hash",
            sa.String(length=128),
            nullable=True,
        ),
    )

    op.add_column(
        "users",
        sa.Column(
            "email_verification_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_users_email_verified",
        "users",
        ["email_verified"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_users_email_verified",
        table_name="users",
    )

    op.drop_column(
        "users",
        "email_verification_expires_at",
    )

    op.drop_column(
        "users",
        "email_verification_token_hash",
    )

    op.drop_column(
        "users",
        "email_verified",
    )