"""
Database dependencies for FastAPI dependency injection.

This module provides dependency injection functions for database sessions
in FastAPI routes. It handles session lifecycle management including
automatic commit on success, rollback on exception, and cleanup.
"""

import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal

# Configure logger
logger = logging.getLogger(__name__)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides a database session.

    The session is automatically managed with proper lifecycle:
    - Created at the start of the request
    - Committed on successful completion
    - Rolled back on exception
    - Closed after the request completes

    This ensures proper transaction boundaries and prevents connection leaks.

    Yields:
        AsyncSession: Database session for the current request

    Raises:
        Any exception from the route handler (after rollback)

    Example:
        @app.get("/items")
        async def read_items(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(Item))
            return result.scalars().all()

        @app.post("/items")
        async def create_item(
            item: ItemCreate,
            db: AsyncSession = Depends(get_db)
        ):
            db_item = Item(**item.model_dump())
            db.add(db_item)
            # Commit happens automatically on success
            return db_item

    Note:
        If you need manual transaction control, you can skip the automatic
        commit by raising an exception or by managing the transaction yourself
        within the route handler.
    """
    async with AsyncSessionLocal() as session:
        try:
            logger.debug("Database session created for request")
            yield session
            await session.commit()
            logger.debug("Database session committed successfully")
        except Exception as e:
            await session.rollback()
            logger.warning(
                "Database session rolled back due to exception",
                extra={"error": str(e)},
                exc_info=True,
            )
            raise
        finally:
            await session.close()
            logger.debug("Database session closed")
