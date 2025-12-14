"""
Tests for Alembic configuration and setup.

This module validates that Alembic is correctly configured for
async SQLAlchemy and can perform basic migration operations.
"""

import pytest
from pathlib import Path
from alembic.config import Config
from alembic import command
from alembic.script import ScriptDirectory


def test_alembic_config_exists():
    """Test that alembic.ini configuration file exists."""
    backend_dir = Path(__file__).parent.parent
    alembic_ini = backend_dir / "alembic.ini"
    assert alembic_ini.exists(), "alembic.ini should exist"


def test_alembic_directory_structure():
    """Test that Alembic directory structure is properly set up."""
    backend_dir = Path(__file__).parent.parent
    alembic_dir = backend_dir / "alembic"

    assert alembic_dir.exists(), "alembic directory should exist"
    assert (alembic_dir / "env.py").exists(), "env.py should exist"
    assert (alembic_dir / "script.py.mako").exists(), "script.py.mako should exist"
    assert (alembic_dir / "versions").exists(), "versions directory should exist"


def test_alembic_config_loads():
    """Test that Alembic configuration loads without errors."""
    backend_dir = Path(__file__).parent.parent
    alembic_ini = str(backend_dir / "alembic.ini")

    config = Config(alembic_ini)
    assert config is not None, "Config should load successfully"

    # Check key configuration options
    script_location = config.get_main_option("script_location")
    assert script_location == "alembic", "Script location should be 'alembic'"


def test_alembic_env_imports():
    """Test that env.py has required functions by checking source code."""
    backend_dir = Path(__file__).parent.parent
    env_path = backend_dir / "alembic" / "env.py"

    env_content = env_path.read_text()

    # Check required functions exist in source
    assert "def run_migrations_offline()" in env_content, \
        "env.py should have run_migrations_offline function"
    assert "def run_migrations_online()" in env_content, \
        "env.py should have run_migrations_online function"
    assert "async def run_async_migrations()" in env_content, \
        "env.py should have run_async_migrations function"
    assert "def do_run_migrations(" in env_content, \
        "env.py should have do_run_migrations function"

    # Check that target_metadata is set
    assert "target_metadata = Base.metadata" in env_content, \
        "env.py should set target_metadata to Base.metadata"


def test_alembic_script_directory():
    """Test that ScriptDirectory can be initialized."""
    backend_dir = Path(__file__).parent.parent
    alembic_ini = str(backend_dir / "alembic.ini")

    config = Config(alembic_ini)
    script = ScriptDirectory.from_config(config)

    assert script is not None, "ScriptDirectory should initialize"
    # The dir is relative, so just check it ends with 'alembic'
    assert script.dir.endswith("alembic"), \
        f"ScriptDirectory should point to alembic directory, got: {script.dir}"


def test_alembic_file_template():
    """Test that file template is configured for timestamp naming."""
    backend_dir = Path(__file__).parent.parent
    alembic_ini = str(backend_dir / "alembic.ini")

    config = Config(alembic_ini)
    file_template = config.get_main_option("file_template")

    # Should use timestamp-based naming
    assert file_template is not None, "file_template should be configured"
    assert "year" in file_template, "file_template should include year"
    assert "month" in file_template, "file_template should include month"
    assert "day" in file_template, "file_template should include day"
    assert "slug" in file_template, "file_template should include slug"


@pytest.mark.asyncio
async def test_alembic_database_connection():
    """Test that Alembic can connect to the database."""
    from app.core.database import engine
    from sqlalchemy import text

    # Test basic database connectivity
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT 1"))
        assert result.scalar() == 1, "Database should be accessible"

    # Verify alembic_version table exists (created by alembic upgrade)
    async with engine.begin() as conn:
        result = await conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'alembic_version'
            )
        """))
        table_exists = result.scalar()
        assert table_exists, "alembic_version table should exist"


def test_migration_template_has_type_hints():
    """Test that migration template includes type hints."""
    backend_dir = Path(__file__).parent.parent
    template_path = backend_dir / "alembic" / "script.py.mako"

    template_content = template_path.read_text()

    # Check for type hints
    assert "-> None:" in template_content, \
        "Template should have type hints on functions"
    assert "from typing import" in template_content, \
        "Template should import typing module"
    assert "Union[str, None]" in template_content, \
        "Template should use Union types for revision identifiers"


def test_env_has_async_support():
    """Test that env.py is configured for async SQLAlchemy."""
    backend_dir = Path(__file__).parent.parent
    env_path = backend_dir / "alembic" / "env.py"

    env_content = env_path.read_text()

    # Check for async imports and usage
    assert "import asyncio" in env_content, \
        "env.py should import asyncio"
    assert "async_engine_from_config" in env_content, \
        "env.py should use async_engine_from_config"
    assert "asyncio.run" in env_content, \
        "env.py should use asyncio.run for running async migrations"
    assert "pool.NullPool" in env_content, \
        "env.py should use NullPool for migrations"


def test_env_has_settings_integration():
    """Test that env.py integrates with application settings."""
    backend_dir = Path(__file__).parent.parent
    env_path = backend_dir / "alembic" / "env.py"

    env_content = env_path.read_text()

    # Check for settings import and usage
    assert "from app.core.config import settings" in env_content, \
        "env.py should import settings"
    assert "settings.DATABASE_URL" in env_content, \
        "env.py should use settings.DATABASE_URL"
    assert "from app.core.database import Base" in env_content, \
        "env.py should import Base"


def test_env_has_comparison_options():
    """Test that env.py has comparison options for accurate autogenerate."""
    backend_dir = Path(__file__).parent.parent
    env_path = backend_dir / "alembic" / "env.py"

    env_content = env_path.read_text()

    # Check for comparison options
    assert "compare_type=True" in env_content, \
        "env.py should enable type comparison"
    assert "compare_server_default=True" in env_content, \
        "env.py should enable server default comparison"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
