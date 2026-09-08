from logging.config import fileConfig
from urllib.parse import quote_plus
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy import pool

from alembic import context

from backend.database import Base
from backend import models


# Load environment variables from .env
load_dotenv()


# Alembic Config object
config = context.config


# Configure Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# Metadata for autogenerate
target_metadata = Base.metadata


def get_database_url() -> str:
    """Build the PostgreSQL connection URL from .env variables."""

    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")
    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT")
    db_name = os.getenv("DB_NAME")

    if not all([db_user, db_password, db_host, db_port, db_name]):
        raise RuntimeError(
            "Database environment variables are not configured"
        )

    # URL-encode username/password so special characters are handled safely.
    return (
        f"postgresql+psycopg://"
        f"{quote_plus(db_user)}:"
        f"{quote_plus(db_password)}@"
        f"{db_host}:{db_port}/{db_name}"
    )


def run_migrations_offline() -> None:
    """Run migrations in offline mode."""

    url = get_database_url()

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in online mode."""

    database_url = get_database_url()

    connectable = create_engine(
        database_url,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()