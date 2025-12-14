"""
Manual validation script for database infrastructure.

This script directly tests the database infrastructure without pytest's
async event loop complications. Run this to verify everything works.
"""

import asyncio
from app.core.database import (
    engine,
    AsyncSessionLocal,
    Base,
    init_db,
    close_db,
    get_db_health,
)
from app.api.dependencies.database import get_db
from sqlalchemy import text


async def test_engine():
    """Test engine creation and connectivity."""
    print("Testing engine connectivity...")
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT 1 as value"))
        value = result.scalar()
        assert value == 1
    print("✓ Engine connectivity test passed")


async def test_session_factory():
    """Test session factory."""
    print("Testing session factory...")
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT current_database() as db"))
        db_name = result.scalar()
        assert db_name == "knowledge_mapper_db"
    print(f"✓ Session factory test passed (database: {db_name})")


async def test_concurrent_sessions():
    """Test multiple concurrent sessions."""
    print("Testing concurrent sessions...")

    async def query_session(i: int):
        async with AsyncSessionLocal() as session:
            result = await session.execute(text(f"SELECT {i} as id"))
            return result.scalar()

    results = await asyncio.gather(*[query_session(i) for i in range(10)])
    assert results == list(range(10))
    print(f"✓ Concurrent sessions test passed (10 sessions)")


async def test_db_health():
    """Test database health check."""
    print("Testing database health check...")
    health = await get_db_health()
    assert health["status"] == "healthy"
    assert health["database"] == "connected"
    print(f"✓ Database health check passed: {health}")


async def test_get_db_dependency():
    """Test get_db dependency."""
    print("Testing get_db dependency...")
    gen = get_db()
    session = await gen.__anext__()
    try:
        result = await session.execute(text("SELECT 'dependency_works' as msg"))
        msg = result.scalar()
        assert msg == "dependency_works"
        print(f"✓ get_db dependency test passed")
    finally:
        # Cleanup
        try:
            await gen.__anext__()
        except StopAsyncIteration:
            pass


async def main():
    """Run all validation tests."""
    print("=" * 60)
    print("DATABASE INFRASTRUCTURE VALIDATION")
    print("=" * 60)

    try:
        # Initialize database
        print("\nInitializing database...")
        await init_db()

        # Run tests
        await test_engine()
        await test_session_factory()
        await test_concurrent_sessions()
        await test_db_health()
        await test_get_db_dependency()

        print("\n" + "=" * 60)
        print("ALL VALIDATION TESTS PASSED ✓")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ Validation failed: {e}")
        raise
    finally:
        # Cleanup
        print("\nClosing database connections...")
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
