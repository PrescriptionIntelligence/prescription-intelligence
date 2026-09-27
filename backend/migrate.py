"""
Prescription Intelligence database migration.

Run from the project root:

    python -m backend.migrate

This migration is intentionally non-destructive.
It adds the new startup architecture without deleting
existing prescription or medicine records.
"""

from sqlalchemy import inspect, text

from backend.database import engine, Base

# Import every model so SQLAlchemy knows about every table.
from backend.models import (
    OrganizationDB,
    UserDB,
    CustomerDB,
    CustomerOrganizationDB,
    CustomerPharmacyLinkRequestDB,
    PrescriptionDB,
    MedicineDB,
    ReviewAuditDB,
)


def column_exists(connection, table_name: str, column_name: str) -> bool:
    inspector = inspect(connection)

    if not inspector.has_table(table_name):
        return False

    columns = inspector.get_columns(table_name)

    return any(
        column["name"] == column_name
        for column in columns
    )


def add_column_if_missing(
    connection,
    table_name: str,
    column_name: str,
    column_definition: str,
):
    if not column_exists(
        connection,
        table_name,
        column_name,
    ):
        connection.execute(
            text(
                f'ALTER TABLE "{table_name}" '
                f'ADD COLUMN "{column_name}" '
                f'{column_definition}'
            )
        )

        print(f"Added {table_name}.{column_name}")


def main():
    print("Starting Prescription Intelligence migration...")

    with engine.begin() as connection:

        # -------------------------------------------------
        # Create new tables
        # -------------------------------------------------

        Base.metadata.create_all(bind=connection)

        print("Verified all tables.")

        # -------------------------------------------------
        # Existing prescriptions table
        # -------------------------------------------------

        add_column_if_missing(
            connection,
            "prescriptions",
            "organization_id",
            "UUID",
        )

        add_column_if_missing(
            connection,
            "prescriptions",
            "uploaded_by_id",
            "UUID",
        )

        add_column_if_missing(
            connection,
            "prescriptions",
            "customer_id",
            "UUID",
        )

        add_column_if_missing(
            connection,
            "prescriptions",
            "review_status",
            "VARCHAR(30) DEFAULT 'pending'",
        )

        add_column_if_missing(
            connection,
            "prescriptions",
            "reviewed_by_id",
            "UUID",
        )

        add_column_if_missing(
            connection,
            "prescriptions",
            "reviewed_at",
            "TIMESTAMP WITH TIME ZONE",
        )

        add_column_if_missing(
            connection,
            "prescriptions",
            "review_notes",
            "TEXT",
        )

        add_column_if_missing(
            connection,
            "prescriptions",
            "safety_flags",
            "JSONB DEFAULT '[]'::jsonb",
        )

        add_column_if_missing(
            connection,
            "prescriptions",
            "updated_at",
            "TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP",
        )

        # -------------------------------------------------
        # Existing medicines table
        # -------------------------------------------------

        add_column_if_missing(
            connection,
            "medicines",
            "strength_components",
            "JSONB DEFAULT '[]'::jsonb",
        )

        add_column_if_missing(
            connection,
            "medicines",
            "daily_dose_components",
            "JSONB DEFAULT '[]'::jsonb",
        )

        # -------------------------------------------------
        # Customer account relationship
        # -------------------------------------------------

        add_column_if_missing(
            connection,
            "customers",
            "user_id",
            "UUID",
        )

        # -------------------------------------------------
        # Customer ↔ Organization association
        # -------------------------------------------------

        if not inspect(connection).has_table(
            "customer_organizations"
        ):
            Base.metadata.create_all(
                bind=connection,
                tables=[
                    CustomerOrganizationDB.__table__
                ],
            )

            print(
                "Created customer_organizations table."
            )
        else:
            print(
                "Verified customer_organizations table."
            )

        # -------------------------------------------------
        # Foreign keys
        #
        # PostgreSQL will reject duplicates, so we check
        # constraint names first.
        # -------------------------------------------------

        inspector = inspect(connection)

        prescription_constraints = {
            item["name"]
            for item in inspector.get_foreign_keys(
                "prescriptions"
            )
        }

        if "fk_prescriptions_organization" not in prescription_constraints:
            connection.execute(
                text(
                    """
                    ALTER TABLE prescriptions
                    ADD CONSTRAINT fk_prescriptions_organization
                    FOREIGN KEY (organization_id)
                    REFERENCES organizations(id)
                    """
                )
            )

        if "fk_prescriptions_uploaded_by" not in prescription_constraints:
            connection.execute(
                text(
                    """
                    ALTER TABLE prescriptions
                    ADD CONSTRAINT fk_prescriptions_uploaded_by
                    FOREIGN KEY (uploaded_by_id)
                    REFERENCES users(id)
                    """
                )
            )

        if "fk_prescriptions_customer" not in prescription_constraints:
            connection.execute(
                text(
                    """
                    ALTER TABLE prescriptions
                    ADD CONSTRAINT fk_prescriptions_customer
                    FOREIGN KEY (customer_id)
                    REFERENCES customers(id)
                    """
                )
            )

        if "fk_prescriptions_reviewed_by" not in prescription_constraints:
            connection.execute(
                text(
                    """
                    ALTER TABLE prescriptions
                    ADD CONSTRAINT fk_prescriptions_reviewed_by
                    FOREIGN KEY (reviewed_by_id)
                    REFERENCES users(id)
                    """
                )
            )

        # -------------------------------------------------
        # Customer → User foreign key
        # -------------------------------------------------

        customer_constraints = {
            item["name"]
            for item in inspector.get_foreign_keys(
                "customers"
            )
        }

        if "fk_customers_user" not in customer_constraints:
            connection.execute(
                text(
                    """
                    ALTER TABLE customers
                    ADD CONSTRAINT fk_customers_user
                    FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    """
                )
            )

        # -------------------------------------------------
        # Indexes
        # -------------------------------------------------

        connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS
                ix_prescriptions_organization_id
                ON prescriptions (organization_id)
                """
            )
        )

        connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS
                ix_prescriptions_customer_id
                ON prescriptions (customer_id)
                """
            )
        )

        connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS
                ix_prescriptions_review_status
                ON prescriptions (review_status)
                """
            )
        )

        connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS
                ix_users_role
                ON users (role)
                """
            )
        )

        connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS
                ix_customers_phone
                ON customers (phone)
                """
            )
        )

        connection.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                ix_customers_user_id_unique
                ON customers (user_id)
                """
            )
        )

    print("")
    print("Migration completed successfully.")
    print("")
    print("Current architecture:")
    print("  Organization")
    print("      ↓")
    print("  Users")
    print("      ├── Admin")
    print("      ├── Pharmacist")
    print("      └── Customer")
    print("              ↓")
    print("          Customer Profile")
    print("              ↓")
    print("          Prescriptions")
    print("              ↓")
    print("       Medicine intelligence")
    print("              ↓")
    print("         Human review")
    print("")
    print("Privacy model:")
    print("  Pharmacy → own organization data")
    print("  Customer → own prescriptions across pharmacies")
    print("  Admin    → platform oversight")


if __name__ == "__main__":
    main()