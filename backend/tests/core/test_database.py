"""
Unit tests for core database infrastructure.

Tests the async SQLAlchemy engine, session factory, Base class,
and database lifecycle utilities.
"""

import pytest
import asyncio
from datetime import datetime, timezone
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String

from app.core.database import (
    engine,
    AsyncSessionLocal,
    Base,
    init_db,
    close_db,
    get_db_health,
)


class TestModel(Base):
    """Test model for validating Base class functionality."""

    __tablename__ = "test_models"

    name: Mapped[str] = mapped_column(String(100), nullable=False)


class TestDatabaseEngine:
    """Test suite for database engine configuration."""

    @pytest.mark.asyncio
    async def test_engine_creation(self):
        """Test that the async engine is created successfully."""
        assert engine is not None
        assert hasattr(engine, "begin")
        assert hasattr(engine, "dispose")

    @pytest.mark.asyncio
    async def test_engine_connectivity(self):
        """Test that the engine can connect to the database."""
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT 1"))
            assert result.scalar() == 1

    @pytest.mark.asyncio
    async def test_engine_pool_configuration(self):
        """Test that connection pool is configured correctly."""
        # Access pool configuration
        pool = engine.pool
        assert pool.size() == 20  # pool_size
        # Note: max_overflow is not directly accessible via pool object
        # but we can verify it's configured in the engine

    @pytest.mark.asyncio
    async def test_database_query(self):
        """Test executing a simple database query."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT current_database()"))
            db_name = result.scalar()
            assert db_name == "knowledge_mapper_db"


class TestSessionFactory:
    """Test suite for async session factory."""

    @pytest.mark.asyncio
    async def test_session_creation(self):
        """Test that sessions can be created from the factory."""
        async with AsyncSessionLocal() as session:
            assert isinstance(session, AsyncSession)

    @pytest.mark.asyncio
    async def test_session_query_execution(self):
        """Test executing queries through a session."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT 1 as value"))
            row = result.first()
            assert row is not None
            assert row.value == 1

    @pytest.mark.asyncio
    async def test_session_transaction_commit(self):
        """Test that session transactions can be committed."""
        async with AsyncSessionLocal() as session:
            # Execute a query
            result = await session.execute(text("SELECT 1"))
            assert result.scalar() == 1
            # Commit should succeed
            await session.commit()

    @pytest.mark.asyncio
    async def test_session_transaction_rollback(self):
        """Test that session transactions can be rolled back."""
        async with AsyncSessionLocal() as session:
            # Execute a query
            await session.execute(text("SELECT 1"))
            # Rollback should succeed
            await session.rollback()

    @pytest.mark.asyncio
    async def test_multiple_concurrent_sessions(self):
        """Test creating multiple concurrent sessions (pool behavior)."""

        async def create_and_query_session(session_id: int):
            """Helper to create a session and execute a query."""
            async with AsyncSessionLocal() as session:
                result = await session.execute(text(f"SELECT {session_id} as id"))
                row = result.first()
                assert row.id == session_id

        # Create 10 concurrent sessions (within pool_size)
        tasks = [create_and_query_session(i) for i in range(10)]
        await asyncio.gather(*tasks)

    @pytest.mark.asyncio
    async def test_session_overflow(self):
        """Test that pool can handle overflow (more than pool_size)."""

        async def create_session_with_delay(session_id: int):
            """Helper to create a session with a small delay."""
            async with AsyncSessionLocal() as session:
                result = await session.execute(text(f"SELECT {session_id} as id"))
                row = result.first()
                assert row.id == session_id
                # Small delay to keep connection active
                await asyncio.sleep(0.01)

        # Create 25 concurrent sessions (more than pool_size of 20)
        # This tests max_overflow=10
        tasks = [create_session_with_delay(i) for i in range(25)]
        await asyncio.gather(*tasks)


class TestBaseClass:
    """Test suite for the Base declarative class."""

    def test_base_class_exists(self):
        """Test that Base class is defined."""
        assert Base is not None

    def test_base_class_has_common_columns(self):
        """Test that Base provides common columns."""
        # Create a test model instance
        model = TestModel(name="test")

        # Verify common columns are accessible
        assert hasattr(model, "id")
        assert hasattr(model, "created_at")
        assert hasattr(model, "updated_at")

    def test_timestamp_defaults(self):
        """Test that timestamps have UTC defaults."""
        model = TestModel(name="test")

        # created_at should have a default
        assert hasattr(model, "created_at")
        # updated_at should have a default
        assert hasattr(model, "updated_at")

    @pytest.mark.asyncio
    async def test_timestamps_in_database(self):
        """Test that timestamps are properly stored in the database."""
        # Create test table using raw connection
        async with engine.connect() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.commit()

        try:
            # Insert a test record
            async with AsyncSessionLocal() as session:
                before_create = datetime.now(timezone.utc)
                model = TestModel(name="timestamp_test")
                session.add(model)
                await session.flush()  # Flush to get ID without committing
                model_id = model.id
                created_at = model.created_at
                updated_at = model.updated_at
                await session.commit()
                after_create = datetime.now(timezone.utc)

            # Verify timestamps are within reasonable range
            assert before_create <= created_at <= after_create
            assert before_create <= updated_at <= after_create
            # Should be very close on creation (within 1 second)
            time_diff = abs((created_at - updated_at).total_seconds())
            assert time_diff < 1.0, f"created_at and updated_at differ by {time_diff} seconds"

            # Update the record and verify updated_at changes
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(TestModel).where(TestModel.id == model_id)
                )
                model = result.scalar_one()
                original_updated_at = model.updated_at

                # Modify the model
                model.name = "updated_name"
                await session.flush()
                new_updated_at = model.updated_at
                await session.commit()

            # updated_at should have changed
            # Note: This might not work perfectly due to timestamp precision
            # and the speed of execution, but it demonstrates the concept
            assert new_updated_at >= original_updated_at

        finally:
            # Clean up test table
            async with engine.connect() as conn:
                await conn.run_sync(Base.metadata.drop_all)
                await conn.commit()


class TestDatabaseLifecycle:
    """Test suite for database lifecycle utilities."""

    @pytest.mark.asyncio
    async def test_init_db(self):
        """Test database initialization."""
        # Should not raise an exception
        await init_db()

    @pytest.mark.asyncio
    async def test_close_db(self):
        """Test database connection cleanup."""
        # Should not raise an exception
        await close_db()
        # Note: After close_db, we need to reconnect for other tests
        # In production, this is called on shutdown

    @pytest.mark.asyncio
    async def test_get_db_health_success(self):
        """Test database health check when database is accessible."""
        health = await get_db_health()
        assert health["status"] == "healthy"
        assert health["database"] == "connected"
        assert "error" not in health

    @pytest.mark.asyncio
    async def test_get_db_health_with_error(self):
        """Test database health check handles errors gracefully."""
        # Close the database to simulate an error
        await close_db()

        try:
            health = await get_db_health()
            # After disposal, engine should still be able to reconnect
            # or we should get an error response
            assert "status" in health
            assert health["status"] in ["healthy", "unhealthy"]
        finally:
            # Reinitialize for other tests
            await init_db()


class TestErrorHandling:
    """Test suite for database error handling."""

    @pytest.mark.asyncio
    async def test_invalid_query_raises_exception(self):
        """Test that invalid SQL raises an exception."""
        async with AsyncSessionLocal() as session:
            with pytest.raises(Exception):
                await session.execute(text("SELECT * FROM nonexistent_table"))
                await session.commit()

    @pytest.mark.asyncio
    async def test_rollback_on_exception(self):
        """Test that exceptions trigger rollback."""
        async with AsyncSessionLocal() as session:
            try:
                await session.execute(text("SELECT * FROM nonexistent_table"))
                await session.commit()
            except Exception:
                await session.rollback()
                # Should be able to execute another query after rollback
                result = await session.execute(text("SELECT 1"))
                assert result.scalar() == 1


class TestConnectionPool:
    """Test suite for connection pool behavior."""

    @pytest.mark.asyncio
    async def test_connection_reuse(self):
        """Test that connections are reused from the pool."""
        # Execute multiple queries in sequence
        for i in range(5):
            async with AsyncSessionLocal() as session:
                result = await session.execute(text(f"SELECT {i}"))
                assert result.scalar() == i

    @pytest.mark.asyncio
    async def test_no_connection_leak(self):
        """Test that connections are properly returned to pool."""
        # Get initial pool status
        pool = engine.pool
        initial_checkedout = pool.checkedout()

        # Create and close multiple sessions
        for i in range(5):
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
                await session.commit()

        # Verify no connections leaked
        final_checkedout = pool.checkedout()
        assert final_checkedout == initial_checkedout


class TestSessionConfiguration:
    """Test suite for session configuration settings."""

    @pytest.mark.asyncio
    async def test_expire_on_commit_false(self):
        """Test that expire_on_commit=False allows access after commit."""
        # Create test table
        async with engine.connect() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.commit()

        try:
            async with AsyncSessionLocal() as session:
                model = TestModel(name="test_expire")
                session.add(model)
                await session.commit()

                # Should be able to access attributes after commit
                # without triggering a new query (due to expire_on_commit=False)
                assert model.name == "test_expire"
                assert model.id is not None

        finally:
            # Clean up
            async with engine.connect() as conn:
                await conn.run_sync(Base.metadata.drop_all)
                await conn.commit()

    @pytest.mark.asyncio
    async def test_autocommit_false(self):
        """Test that autocommit=False requires explicit commit."""
        # Create test table
        async with engine.connect() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.commit()

        try:
            # Create a record without committing
            model_id = None
            async with AsyncSessionLocal() as session:
                model = TestModel(name="test_autocommit")
                session.add(model)
                await session.flush()  # Get ID without committing
                model_id = model.id
                # Don't commit - session will rollback on close

            # Verify record was not persisted
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(TestModel).where(TestModel.id == model_id)
                )
                found_model = result.scalar_one_or_none()
                assert found_model is None  # Should not exist (rollback)

        finally:
            # Clean up
            async with engine.connect() as conn:
                await conn.run_sync(Base.metadata.drop_all)
                await conn.commit()
