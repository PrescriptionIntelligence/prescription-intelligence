"""full schema: organizations, users, customers, prescriptions v2, medicines v2

Revision ID: e1a2b3c4d5e6
Revises: 7f4ecab9d546
Create Date: 2026-09-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "7f4ecab9d546"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add all tables and columns that the current models require
    but are not yet present in the database.

    Uses IF NOT EXISTS / try/except patterns so this migration
    is safe to run on databases that may already have some of
    these objects.
    """

    # ------------------------------------------------------------------
    # ORGANIZATIONS
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS organizations (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name        VARCHAR(200) NOT NULL,
            slug        VARCHAR(100) NOT NULL UNIQUE,
            phone       VARCHAR(30),
            email       VARCHAR(255),
            address     TEXT,
            is_active   BOOLEAN NOT NULL DEFAULT TRUE,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_organizations_slug
            ON organizations(slug)
    """)

    # ------------------------------------------------------------------
    # USERS
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id  UUID REFERENCES organizations(id),
            name             VARCHAR(200) NOT NULL,
            email            VARCHAR(255) NOT NULL UNIQUE,
            password_hash    VARCHAR(500) NOT NULL,
            role             VARCHAR(30) NOT NULL DEFAULT 'pharmacist',
            is_active        BOOLEAN NOT NULL DEFAULT TRUE,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_login_at    TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_users_email ON users(email)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_users_organization_id ON users(organization_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_users_role ON users(role)")

    # ------------------------------------------------------------------
    # CUSTOMERS
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id  UUID NOT NULL REFERENCES organizations(id),
            user_id          UUID UNIQUE REFERENCES users(id),
            customer_code    VARCHAR(50) NOT NULL UNIQUE,
            name             VARCHAR(200) NOT NULL,
            phone            VARCHAR(30),
            email            VARCHAR(255),
            date_of_birth    TIMESTAMPTZ,
            address          TEXT,
            notes            TEXT,
            is_active        BOOLEAN NOT NULL DEFAULT TRUE,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_customers_customer_code ON customers(customer_code)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_customers_organization_id ON customers(organization_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_customers_phone ON customers(phone)")
    
    # ------------------------------------------------------------------
    # PRESCRIPTIONS — add missing columns
    # ------------------------------------------------------------------

    # updated_at
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'prescriptions' AND column_name = 'updated_at'
            ) THEN
                ALTER TABLE prescriptions ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
            END IF;
        END
        $$;
    """)

    # organization_id
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'prescriptions' AND column_name = 'organization_id'
            ) THEN
                ALTER TABLE prescriptions ADD COLUMN organization_id UUID REFERENCES organizations(id);
            END IF;
        END
        $$;
    """)

    # uploaded_by_id
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'prescriptions' AND column_name = 'uploaded_by_id'
            ) THEN
                ALTER TABLE prescriptions ADD COLUMN uploaded_by_id UUID REFERENCES users(id);
            END IF;
        END
        $$;
    """)

    # customer_id
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'prescriptions' AND column_name = 'customer_id'
            ) THEN
                ALTER TABLE prescriptions ADD COLUMN customer_id UUID REFERENCES customers(id);
            END IF;
        END
        $$;
    """)

    # review_status
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'prescriptions' AND column_name = 'review_status'
            ) THEN
                ALTER TABLE prescriptions ADD COLUMN review_status VARCHAR(30) NOT NULL DEFAULT 'pending';
            END IF;
        END
        $$;
    """)

    # reviewed_by_id
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'prescriptions' AND column_name = 'reviewed_by_id'
            ) THEN
                ALTER TABLE prescriptions ADD COLUMN reviewed_by_id UUID REFERENCES users(id);
            END IF;
        END
        $$;
    """)

    # reviewed_at
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'prescriptions' AND column_name = 'reviewed_at'
            ) THEN
                ALTER TABLE prescriptions ADD COLUMN reviewed_at TIMESTAMPTZ;
            END IF;
        END
        $$;
    """)

    # review_notes
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'prescriptions' AND column_name = 'review_notes'
            ) THEN
                ALTER TABLE prescriptions ADD COLUMN review_notes TEXT;
            END IF;
        END
        $$;
    """)

    # safety_flags (JSONB)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'prescriptions' AND column_name = 'safety_flags'
            ) THEN
                ALTER TABLE prescriptions ADD COLUMN safety_flags JSONB NOT NULL DEFAULT '[]';
            END IF;
        END
        $$;
    """)

    # ------------------------------------------------------------------
    # PRESCRIPTIONS — indexes
    # ------------------------------------------------------------------
    op.execute("CREATE INDEX IF NOT EXISTS ix_prescriptions_organization_id ON prescriptions(organization_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_prescriptions_uploaded_by_id ON prescriptions(uploaded_by_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_prescriptions_customer_id ON prescriptions(customer_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_prescriptions_review_status ON prescriptions(review_status)")

    # ------------------------------------------------------------------
    # MEDICINES — add missing columns
    # ------------------------------------------------------------------

    # strength_value: change from float to text (preserves "3+2" etc.)
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'medicines'
                  AND column_name = 'strength_value'
                  AND data_type = 'double precision'
            ) THEN
                ALTER TABLE medicines ALTER COLUMN strength_value TYPE VARCHAR(100) USING strength_value::VARCHAR;
            END IF;
        END
        $$;
    """)

    # strength_components
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'medicines' AND column_name = 'strength_components'
            ) THEN
                ALTER TABLE medicines ADD COLUMN strength_components JSONB NOT NULL DEFAULT '[]';
            END IF;
        END
        $$;
    """)

    # dose_unit
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'medicines' AND column_name = 'dose_unit'
            ) THEN
                ALTER TABLE medicines ADD COLUMN dose_unit VARCHAR(50);
            END IF;
        END
        $$;
    """)

    # daily_dose_components
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'medicines' AND column_name = 'daily_dose_components'
            ) THEN
                ALTER TABLE medicines ADD COLUMN daily_dose_components JSONB NOT NULL DEFAULT '[]';
            END IF;
        END
        $$;
    """)


def downgrade() -> None:
    """Remove the additions made in this migration."""
    op.execute("DROP INDEX IF EXISTS ix_prescriptions_review_status")
    op.execute("DROP INDEX IF EXISTS ix_prescriptions_customer_id")
    op.execute("DROP INDEX IF EXISTS ix_prescriptions_uploaded_by_id")
    op.execute("DROP INDEX IF EXISTS ix_prescriptions_organization_id")
    op.execute("DROP TABLE IF EXISTS customers")
    op.execute("DROP TABLE IF EXISTS users")
    op.execute("DROP TABLE IF EXISTS organizations")