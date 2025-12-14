"""
Alembic environment configuration for async SQLAlchemy.

This module configures Alembic to work with async SQLAlchemy, including:
- Async database engine configuration
- Model metadata import for autogenerate support
- Settings integration from application config
- Both offline and online migration modes
- Configuration loaded from pyproject.toml
"""

import asyncio
import sys
import tomllib
from pathlib import Path
from logging.config import dictConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Add backend directory to Python path for imports
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.core.database import Base

# Import all models for autogenerate support
# Note: As new models are added to the application, they must be imported here
# for Alembic's autogenerate to detect them.
from app.models.tenant import Tenant
from app.models.user import User
from app.models.oauth_provider import OAuthProvider, ProviderType

# Alembic Config object
config = context.config

# Load configuration from pyproject.toml
pyproject_path = backend_dir / "pyproject.toml"
if pyproject_path.exists():
    with open(pyproject_path, "rb") as f:
        pyproject_data = tomllib.load(f)

    alembic_config = pyproject_data.get("tool", {}).get("alembic", {})

    # Set Alembic configuration from pyproject.toml
    if "script_location" in alembic_config:
        config.set_main_option("script_location", alembic_config["script_location"])
    if "file_template" in alembic_config:
        config.set_main_option("file_template", alembic_config["file_template"])
    if "prepend_sys_path" in alembic_config:
        config.set_main_option("prepend_sys_path", alembic_config["prepend_sys_path"])
    if "version_path_separator" in alembic_config:
        config.set_main_option("version_path_separator", alembic_config["version_path_separator"])

# Configure basic logging
dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "generic": {
            "format": "%(levelname)-5.5s [%(name)s] %(message)s",
            "datefmt": "%H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
            "formatter": "generic",
        },
    },
    "loggers": {
        "root": {
            "level": "WARN",
            "handlers": ["console"],
        },
        "sqlalchemy.engine": {
            "level": "WARN",
            "handlers": [],
        },
        "alembic": {
            "level": "INFO",
            "handlers": [],
        },
    },
})

# Set metadata for autogenerate support
# This tells Alembic which models to track for schema changes
target_metadata = Base.metadata

# Override sqlalchemy.url from application settings
# Migrations use MIGRATION_DATABASE_URL (knowledge_mapper_migration_user with BYPASSRLS)
# This allows migrations to bypass RLS policies for schema management
config.set_main_option("sqlalchemy.url", settings.MIGRATION_DATABASE_URL)


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine,
    though an Engine is acceptable here as well. By skipping the Engine
    creation we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output for manual application.

    This is useful for generating SQL scripts for review or for
    high-security production environments where migrations must be
    manually reviewed and applied.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,  # Detect column type changes
        compare_server_default=True,  # Detect default value changes
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """
    Run migrations with an active database connection.

    This is called by run_async_migrations after establishing an
    async connection. The connection is run in sync mode using
    run_sync() to execute the migrations.

    Args:
        connection: SQLAlchemy Connection object
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,  # Detect column type changes
        compare_server_default=True,  # Detect default value changes
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Create async engine and run migrations asynchronously.

    This function:
    1. Creates an async engine from the configuration
    2. Establishes an async connection
    3. Runs migrations in sync mode via run_sync()
    4. Properly disposes of the engine

    Uses NullPool to avoid connection pooling during migrations,
    which simplifies connection lifecycle management.
    """
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # No connection pooling for migrations
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    In this scenario we create an async Engine and run migrations
    directly against the database. This is the standard mode for
    development and automated deployment.

    The migrations are run inside an async context using asyncio.run().
    """
    asyncio.run(run_async_migrations())


# Entry point: determine offline vs online mode
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
