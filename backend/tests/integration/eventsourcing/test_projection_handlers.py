"""
Integration tests for projection handlers.

Tests that projection handlers correctly create and update database records
when processing domain events against real PostgreSQL.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.eventsourcing.events.extraction import (
    ExtractionCompleted,
    ExtractionProcessFailed,
    ExtractionRequested,
    ExtractionStarted,
    RelationshipDiscovered,
)
from app.eventsourcing.events.scraping import EntityExtracted
from app.eventsourcing.projections.extraction import (
    EntityProjectionHandler,
    ExtractionProcessProjectionHandler,
    RelationshipProjectionHandler,
)


# =============================================================================
# Fixtures
# =============================================================================


from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.core.config import settings


# Create a separate session factory for tests using migration user (BYPASSRLS)
def _get_migration_user_url():
    """Get database URL with migration user credentials for bypassing RLS."""
    base_url = settings.DATABASE_URL
    # Replace app_user with migration_user
    return base_url.replace(
        "knowledge_mapper_app_user:app_password_dev",
        "knowledge_mapper_migration_user:migration_password_dev"
    )


_test_engine = create_async_engine(_get_migration_user_url(), echo=False)
TestSessionLocal = async_sessionmaker(
    _test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@pytest.fixture
async def db_session():
    """Create a database session for tests using migration user (BYPASSRLS)."""
    async with TestSessionLocal() as session:
        yield session
        # Rollback any uncommitted changes
        await session.rollback()


@pytest.fixture
async def entity_handler():
    """Create EntityProjectionHandler instance with test session factory."""
    return EntityProjectionHandler(session_factory=TestSessionLocal)


@pytest.fixture
async def process_handler():
    """Create ExtractionProcessProjectionHandler instance with test session factory."""
    return ExtractionProcessProjectionHandler(session_factory=TestSessionLocal)


@pytest.fixture
async def relationship_handler():
    """Create RelationshipProjectionHandler instance with test session factory."""
    return RelationshipProjectionHandler(session_factory=TestSessionLocal)


@pytest.fixture
async def test_tenant(db_session: AsyncSession):
    """Create a test tenant for projection tests."""
    tenant_id = uuid4()
    unique_slug = f"test-projection-{tenant_id.hex[:8]}"

    await db_session.execute(
        text("""
            INSERT INTO tenants (id, slug, name, settings, is_active, created_at, updated_at)
            VALUES (:id, :slug, :name, CAST(:settings AS jsonb), TRUE, NOW(), NOW())
        """),
        {
            "id": tenant_id,
            "slug": unique_slug,
            "name": "Test Projection Tenant",
            "settings": "{}",
        },
    )
    await db_session.commit()

    yield tenant_id

    # Cleanup tenant and related data
    await db_session.execute(
        text("DELETE FROM entity_relationships WHERE tenant_id = :id"),
        {"id": tenant_id},
    )
    await db_session.execute(
        text("DELETE FROM extracted_entities WHERE tenant_id = :id"),
        {"id": tenant_id},
    )
    await db_session.execute(
        text("DELETE FROM extraction_processes WHERE tenant_id = :id"),
        {"id": tenant_id},
    )
    await db_session.execute(
        text("DELETE FROM scraped_pages WHERE tenant_id = :id"),
        {"id": tenant_id},
    )
    await db_session.execute(
        text("DELETE FROM scraping_jobs WHERE tenant_id = :id"),
        {"id": tenant_id},
    )
    await db_session.execute(
        text("DELETE FROM tenants WHERE id = :id"),
        {"id": tenant_id},
    )
    await db_session.commit()


@pytest.fixture
async def test_scraped_page(db_session: AsyncSession, test_tenant):
    """Create a test scraped page for entity tests (FK requirement)."""
    page_id = uuid4()
    job_id = uuid4()

    # Create scraping job first (matching the actual table schema)
    await db_session.execute(
        text("""
            INSERT INTO scraping_jobs (
                id, tenant_id, created_by_user_id, name, start_url,
                allowed_domains, crawl_depth, max_pages,
                status, created_at, updated_at
            ) VALUES (
                :id, :tenant_id, :user_id, :name, :url,
                '[]'::jsonb, 3, 100,
                'completed', NOW(), NOW()
            )
        """),
        {
            "id": job_id,
            "tenant_id": test_tenant,
            "user_id": "test-user-integration",
            "name": "Test Job",
            "url": "https://example.com",
        },
    )

    # Create scraped page (matching actual table schema)
    await db_session.execute(
        text("""
            INSERT INTO scraped_pages (
                id, tenant_id, job_id, url, content_hash, html_content, text_content,
                http_status, content_type, depth, extraction_status, crawled_at,
                created_at, updated_at
            ) VALUES (
                :id, :tenant_id, :job_id, :url, :hash, :html, :text_content,
                200, 'text/html', 0, 'pending', NOW(),
                NOW(), NOW()
            )
        """),
        {
            "id": page_id,
            "tenant_id": test_tenant,
            "job_id": job_id,
            "url": "https://example.com/test-page",
            "hash": "testhash123",
            "html": "<html><body>Test content</body></html>",
            "text_content": "Test content",
        },
    )
    await db_session.commit()

    yield page_id


# =============================================================================
# EntityProjectionHandler Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
class TestEntityProjectionHandler:
    """Tests for EntityProjectionHandler creating extracted_entities records."""

    async def test_creates_entity_record(
        self,
        entity_handler: EntityProjectionHandler,
        db_session: AsyncSession,
        test_tenant,
        test_scraped_page,
    ):
        """Test handler creates an extracted_entities record."""
        entity_id = uuid4()
        job_id = uuid4()

        event = EntityExtracted(
            aggregate_id=uuid4(),
            aggregate_type="ExtractedEntity",
            aggregate_version=1,
            tenant_id=test_tenant,
            entity_id=entity_id,
            page_id=test_scraped_page,
            job_id=job_id,
            entity_type="function",
            name="process_data",
            normalized_name="process_data",
            description="Processes input data",
            properties={"signature": "def process_data(x: int) -> str"},
            extraction_method="llm_ollama",
            confidence_score=0.95,
            source_text="def process_data(x: int) -> str:",
        )

        await entity_handler.handle(event)

        # Verify record created
        result = await db_session.execute(
            text("SELECT * FROM extracted_entities WHERE id = :id"),
            {"id": entity_id},
        )
        row = result.mappings().fetchone()

        assert row is not None
        assert row["name"] == "process_data"
        assert row["entity_type"] == "function"
        assert row["confidence_score"] == 0.95
        assert row["extraction_method"] == "llm_ollama"
        assert row["tenant_id"] == test_tenant

    async def test_entity_projection_is_idempotent(
        self,
        entity_handler: EntityProjectionHandler,
        db_session: AsyncSession,
        test_tenant,
        test_scraped_page,
    ):
        """Test handling same event twice produces same result (idempotency)."""
        entity_id = uuid4()
        job_id = uuid4()

        event = EntityExtracted(
            aggregate_id=uuid4(),
            aggregate_type="ExtractedEntity",
            aggregate_version=1,
            tenant_id=test_tenant,
            entity_id=entity_id,
            page_id=test_scraped_page,
            job_id=job_id,
            entity_type="class",
            name="DataProcessor",
            normalized_name="dataprocessor",
            properties={"methods": ["process", "validate"]},
            extraction_method="llm_ollama",
            confidence_score=0.92,
        )

        # Handle twice
        await entity_handler.handle(event)
        await entity_handler.handle(event)

        # Verify only one record exists
        result = await db_session.execute(
            text("SELECT COUNT(*) as cnt FROM extracted_entities WHERE id = :id"),
            {"id": entity_id},
        )
        count = result.scalar()

        assert count == 1

    async def test_entity_type_mapping(
        self,
        entity_handler: EntityProjectionHandler,
        db_session: AsyncSession,
        test_tenant,
        test_scraped_page,
    ):
        """Test entity type string is correctly mapped to enum value."""
        entity_id = uuid4()

        event = EntityExtracted(
            aggregate_id=uuid4(),
            aggregate_type="ExtractedEntity",
            aggregate_version=1,
            tenant_id=test_tenant,
            entity_id=entity_id,
            page_id=test_scraped_page,
            job_id=uuid4(),
            entity_type="FUNCTION",  # Uppercase - should be mapped
            name="test_func",
            normalized_name="test_func",
            properties={},
            extraction_method="llm_ollama",
            confidence_score=0.9,
        )

        await entity_handler.handle(event)

        result = await db_session.execute(
            text("SELECT entity_type FROM extracted_entities WHERE id = :id"),
            {"id": entity_id},
        )
        entity_type = result.scalar()

        assert entity_type == "function"  # Normalized to lowercase


# =============================================================================
# ExtractionProcessProjectionHandler Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
class TestExtractionProcessProjectionHandler:
    """Tests for ExtractionProcessProjectionHandler creating extraction_processes records."""

    async def test_creates_process_record_on_requested(
        self,
        process_handler: ExtractionProcessProjectionHandler,
        db_session: AsyncSession,
        test_tenant,
        test_scraped_page,
    ):
        """Test handler creates extraction_processes record on ExtractionRequested."""
        process_id = uuid4()

        event = ExtractionRequested(
            aggregate_id=process_id,
            aggregate_type="ExtractionProcess",
            aggregate_version=1,
            tenant_id=test_tenant,
            page_id=test_scraped_page,
            page_url="https://docs.example.com/api",
            content_hash="hash123",
            extraction_config={"model": "llama3.2"},
            requested_at=datetime.now(timezone.utc),
        )

        await process_handler.handle(event)

        # Verify record created
        result = await db_session.execute(
            text("SELECT * FROM extraction_processes WHERE id = :id"),
            {"id": process_id},
        )
        row = result.mappings().fetchone()

        assert row is not None
        assert row["status"] == "pending"
        assert row["page_url"] == "https://docs.example.com/api"
        assert row["tenant_id"] == test_tenant

    async def test_updates_process_on_started(
        self,
        process_handler: ExtractionProcessProjectionHandler,
        db_session: AsyncSession,
        test_tenant,
        test_scraped_page,
    ):
        """Test handler updates status to processing on ExtractionStarted."""
        process_id = uuid4()

        # First create the process
        requested_event = ExtractionRequested(
            aggregate_id=process_id,
            aggregate_type="ExtractionProcess",
            aggregate_version=1,
            tenant_id=test_tenant,
            page_id=test_scraped_page,
            page_url="https://example.com",
            content_hash="hash",
            extraction_config={},
            requested_at=datetime.now(timezone.utc),
        )
        await process_handler.handle(requested_event)

        # Now start it
        started_event = ExtractionStarted(
            aggregate_id=process_id,
            aggregate_type="ExtractionProcess",
            aggregate_version=2,
            tenant_id=test_tenant,
            page_id=test_scraped_page,
            worker_id="worker-integration-1",
            started_at=datetime.now(timezone.utc),
        )
        await process_handler.handle(started_event)

        # Verify status updated
        result = await db_session.execute(
            text("SELECT status, worker_id FROM extraction_processes WHERE page_id = :page_id"),
            {"page_id": test_scraped_page},
        )
        row = result.mappings().fetchone()

        assert row is not None
        assert row["status"] == "processing"
        assert row["worker_id"] == "worker-integration-1"

    async def test_updates_process_on_completed(
        self,
        process_handler: ExtractionProcessProjectionHandler,
        db_session: AsyncSession,
        test_tenant,
        test_scraped_page,
    ):
        """Test handler updates status to completed on ExtractionCompleted."""
        process_id = uuid4()

        # Create and start process
        requested_event = ExtractionRequested(
            aggregate_id=process_id,
            aggregate_type="ExtractionProcess",
            aggregate_version=1,
            tenant_id=test_tenant,
            page_id=test_scraped_page,
            page_url="https://example.com",
            content_hash="hash",
            extraction_config={},
            requested_at=datetime.now(timezone.utc),
        )
        await process_handler.handle(requested_event)

        started_event = ExtractionStarted(
            aggregate_id=process_id,
            aggregate_type="ExtractionProcess",
            aggregate_version=2,
            tenant_id=test_tenant,
            page_id=test_scraped_page,
            worker_id="worker-1",
            started_at=datetime.now(timezone.utc),
        )
        await process_handler.handle(started_event)

        # Complete
        completed_event = ExtractionCompleted(
            aggregate_id=process_id,
            aggregate_type="ExtractionProcess",
            aggregate_version=3,
            tenant_id=test_tenant,
            page_id=test_scraped_page,
            entity_count=10,
            relationship_count=5,
            duration_ms=2500,
            extraction_method="llm_ollama",
            completed_at=datetime.now(timezone.utc),
        )
        await process_handler.handle(completed_event)

        # Verify status updated
        result = await db_session.execute(
            text("""
                SELECT status, entity_count, relationship_count, duration_ms
                FROM extraction_processes WHERE page_id = :page_id
            """),
            {"page_id": test_scraped_page},
        )
        row = result.mappings().fetchone()

        assert row is not None
        assert row["status"] == "completed"
        assert row["entity_count"] == 10
        assert row["relationship_count"] == 5
        assert row["duration_ms"] == 2500

    async def test_updates_process_on_failed(
        self,
        process_handler: ExtractionProcessProjectionHandler,
        db_session: AsyncSession,
        test_tenant,
        test_scraped_page,
    ):
        """Test handler updates status on ExtractionProcessFailed."""
        process_id = uuid4()

        # Create and start
        requested_event = ExtractionRequested(
            aggregate_id=process_id,
            aggregate_type="ExtractionProcess",
            aggregate_version=1,
            tenant_id=test_tenant,
            page_id=test_scraped_page,
            page_url="https://example.com",
            content_hash="hash",
            extraction_config={},
            requested_at=datetime.now(timezone.utc),
        )
        await process_handler.handle(requested_event)

        started_event = ExtractionStarted(
            aggregate_id=process_id,
            aggregate_type="ExtractionProcess",
            aggregate_version=2,
            tenant_id=test_tenant,
            page_id=test_scraped_page,
            worker_id="worker-1",
            started_at=datetime.now(timezone.utc),
        )
        await process_handler.handle(started_event)

        # Fail (retryable)
        failed_event = ExtractionProcessFailed(
            aggregate_id=process_id,
            aggregate_type="ExtractionProcess",
            aggregate_version=3,
            tenant_id=test_tenant,
            page_id=test_scraped_page,
            error_message="LLM timeout after 30s",
            error_type="TIMEOUT",
            retry_count=0,
            retryable=True,
            failed_at=datetime.now(timezone.utc),
        )
        await process_handler.handle(failed_event)

        # Verify status (retryable failures get "retrying" status)
        result = await db_session.execute(
            text("""
                SELECT status, last_error, last_error_type
                FROM extraction_processes WHERE page_id = :page_id
            """),
            {"page_id": test_scraped_page},
        )
        row = result.mappings().fetchone()

        assert row is not None
        assert row["status"] == "retrying"
        assert row["last_error"] == "LLM timeout after 30s"
        assert row["last_error_type"] == "TIMEOUT"

    async def test_process_projection_is_idempotent(
        self,
        process_handler: ExtractionProcessProjectionHandler,
        db_session: AsyncSession,
        test_tenant,
        test_scraped_page,
    ):
        """Test handling same ExtractionRequested event twice is idempotent."""
        process_id = uuid4()

        event = ExtractionRequested(
            aggregate_id=process_id,
            aggregate_type="ExtractionProcess",
            aggregate_version=1,
            tenant_id=test_tenant,
            page_id=test_scraped_page,
            page_url="https://example.com",
            content_hash="hash",
            extraction_config={},
            requested_at=datetime.now(timezone.utc),
        )

        # Handle twice
        await process_handler.handle(event)
        await process_handler.handle(event)

        # Verify only one record (upsert based on page_id)
        result = await db_session.execute(
            text("SELECT COUNT(*) as cnt FROM extraction_processes WHERE page_id = :page_id"),
            {"page_id": test_scraped_page},
        )
        count = result.scalar()

        assert count == 1


# =============================================================================
# RelationshipProjectionHandler Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
class TestRelationshipProjectionHandler:
    """Tests for RelationshipProjectionHandler creating entity_relationships records."""

    async def test_creates_relationship_record(
        self,
        relationship_handler: RelationshipProjectionHandler,
        entity_handler: EntityProjectionHandler,
        db_session: AsyncSession,
        test_tenant,
        test_scraped_page,
    ):
        """Test handler creates entity_relationships record when entities exist."""
        job_id = uuid4()

        # First create source entity
        source_entity_id = uuid4()
        source_event = EntityExtracted(
            aggregate_id=uuid4(),
            aggregate_type="ExtractedEntity",
            aggregate_version=1,
            tenant_id=test_tenant,
            entity_id=source_entity_id,
            page_id=test_scraped_page,
            job_id=job_id,
            entity_type="class",
            name="DataProcessor",
            normalized_name="dataprocessor",
            properties={},
            extraction_method="llm_ollama",
            confidence_score=0.95,
        )
        await entity_handler.handle(source_event)

        # Create target entity
        target_entity_id = uuid4()
        target_event = EntityExtracted(
            aggregate_id=uuid4(),
            aggregate_type="ExtractedEntity",
            aggregate_version=1,
            tenant_id=test_tenant,
            entity_id=target_entity_id,
            page_id=test_scraped_page,
            job_id=job_id,
            entity_type="function",
            name="process_data",
            normalized_name="process_data",
            properties={},
            extraction_method="llm_ollama",
            confidence_score=0.92,
        )
        await entity_handler.handle(target_event)

        # Now create relationship
        relationship_id = uuid4()
        relationship_event = RelationshipDiscovered(
            aggregate_id=uuid4(),
            aggregate_type="ExtractionProcess",
            aggregate_version=3,
            tenant_id=test_tenant,
            relationship_id=relationship_id,
            page_id=test_scraped_page,
            source_entity_name="DataProcessor",
            target_entity_name="process_data",
            relationship_type="CALLS",
            confidence_score=0.88,
            context="DataProcessor.run() calls process_data()",
        )
        await relationship_handler.handle(relationship_event)

        # Verify relationship created
        result = await db_session.execute(
            text("SELECT * FROM entity_relationships WHERE id = :id"),
            {"id": relationship_id},
        )
        row = result.mappings().fetchone()

        assert row is not None
        assert row["source_entity_id"] == source_entity_id
        assert row["target_entity_id"] == target_entity_id
        assert row["relationship_type"] == "CALLS"
        assert row["confidence_score"] == 0.88
        assert row["tenant_id"] == test_tenant

    async def test_relationship_skipped_when_source_entity_missing(
        self,
        relationship_handler: RelationshipProjectionHandler,
        db_session: AsyncSession,
        test_tenant,
        test_scraped_page,
    ):
        """Test handler skips relationship when source entity doesn't exist."""
        relationship_id = uuid4()

        event = RelationshipDiscovered(
            aggregate_id=uuid4(),
            aggregate_type="ExtractionProcess",
            aggregate_version=1,
            tenant_id=test_tenant,
            relationship_id=relationship_id,
            page_id=test_scraped_page,
            source_entity_name="NonExistentSource",
            target_entity_name="SomeTarget",
            relationship_type="USES",
            confidence_score=0.85,
        )

        # Should not raise, just skip
        await relationship_handler.handle(event)

        # Verify no relationship created
        result = await db_session.execute(
            text("SELECT COUNT(*) as cnt FROM entity_relationships WHERE id = :id"),
            {"id": relationship_id},
        )
        count = result.scalar()

        assert count == 0

    async def test_relationship_projection_is_idempotent(
        self,
        relationship_handler: RelationshipProjectionHandler,
        entity_handler: EntityProjectionHandler,
        db_session: AsyncSession,
        test_tenant,
        test_scraped_page,
    ):
        """Test handling same relationship event twice is idempotent."""
        job_id = uuid4()

        # Create both entities
        source_id = uuid4()
        target_id = uuid4()

        await entity_handler.handle(
            EntityExtracted(
                aggregate_id=uuid4(),
                aggregate_type="ExtractedEntity",
                aggregate_version=1,
                tenant_id=test_tenant,
                entity_id=source_id,
                page_id=test_scraped_page,
                job_id=job_id,
                entity_type="class",
                name="Source",
                normalized_name="source",
                properties={},
                extraction_method="llm_ollama",
                confidence_score=0.9,
            )
        )

        await entity_handler.handle(
            EntityExtracted(
                aggregate_id=uuid4(),
                aggregate_type="ExtractedEntity",
                aggregate_version=1,
                tenant_id=test_tenant,
                entity_id=target_id,
                page_id=test_scraped_page,
                job_id=job_id,
                entity_type="class",
                name="Target",
                normalized_name="target",
                properties={},
                extraction_method="llm_ollama",
                confidence_score=0.9,
            )
        )

        # Create relationship event
        relationship_id = uuid4()
        event = RelationshipDiscovered(
            aggregate_id=uuid4(),
            aggregate_type="ExtractionProcess",
            aggregate_version=1,
            tenant_id=test_tenant,
            relationship_id=relationship_id,
            page_id=test_scraped_page,
            source_entity_name="Source",
            target_entity_name="Target",
            relationship_type="EXTENDS",
            confidence_score=0.95,
        )

        # Handle twice
        await relationship_handler.handle(event)
        await relationship_handler.handle(event)

        # Verify only one relationship
        result = await db_session.execute(
            text("SELECT COUNT(*) as cnt FROM entity_relationships WHERE id = :id"),
            {"id": relationship_id},
        )
        count = result.scalar()

        assert count == 1


# =============================================================================
# End-to-End Projection Flow Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
class TestProjectionFlowEndToEnd:
    """Tests for complete projection flow from events to database records."""

    async def test_full_extraction_flow_projections(
        self,
        process_handler: ExtractionProcessProjectionHandler,
        entity_handler: EntityProjectionHandler,
        relationship_handler: RelationshipProjectionHandler,
        db_session: AsyncSession,
        test_tenant,
        test_scraped_page,
    ):
        """Test complete extraction flow updates all projections correctly."""
        process_id = uuid4()
        job_id = uuid4()

        # Step 1: Request extraction
        await process_handler.handle(
            ExtractionRequested(
                aggregate_id=process_id,
                aggregate_type="ExtractionProcess",
                aggregate_version=1,
                tenant_id=test_tenant,
                page_id=test_scraped_page,
                page_url="https://docs.example.com/api",
                content_hash="dochash",
                extraction_config={"model": "llama3.2"},
                requested_at=datetime.now(timezone.utc),
            )
        )

        # Step 2: Start extraction
        await process_handler.handle(
            ExtractionStarted(
                aggregate_id=process_id,
                aggregate_type="ExtractionProcess",
                aggregate_version=2,
                tenant_id=test_tenant,
                page_id=test_scraped_page,
                worker_id="celery-worker-1",
                started_at=datetime.now(timezone.utc),
            )
        )

        # Step 3: Extract entities
        entity_1_id = uuid4()
        await entity_handler.handle(
            EntityExtracted(
                aggregate_id=process_id,
                aggregate_type="ExtractedEntity",
                aggregate_version=3,
                tenant_id=test_tenant,
                entity_id=entity_1_id,
                page_id=test_scraped_page,
                job_id=job_id,
                entity_type="function",
                name="main",
                normalized_name="main",
                properties={"async": True},
                extraction_method="llm_ollama",
                confidence_score=0.97,
            )
        )

        entity_2_id = uuid4()
        await entity_handler.handle(
            EntityExtracted(
                aggregate_id=process_id,
                aggregate_type="ExtractedEntity",
                aggregate_version=4,
                tenant_id=test_tenant,
                entity_id=entity_2_id,
                page_id=test_scraped_page,
                job_id=job_id,
                entity_type="class",
                name="Application",
                normalized_name="application",
                properties={},
                extraction_method="llm_ollama",
                confidence_score=0.95,
            )
        )

        # Step 4: Discover relationship
        relationship_id = uuid4()
        await relationship_handler.handle(
            RelationshipDiscovered(
                aggregate_id=process_id,
                aggregate_type="ExtractionProcess",
                aggregate_version=5,
                tenant_id=test_tenant,
                relationship_id=relationship_id,
                page_id=test_scraped_page,
                source_entity_name="Application",
                target_entity_name="main",
                relationship_type="CALLS",
                confidence_score=0.93,
            )
        )

        # Step 5: Complete extraction
        await process_handler.handle(
            ExtractionCompleted(
                aggregate_id=process_id,
                aggregate_type="ExtractionProcess",
                aggregate_version=6,
                tenant_id=test_tenant,
                page_id=test_scraped_page,
                entity_count=2,
                relationship_count=1,
                duration_ms=3500,
                extraction_method="llm_ollama",
                completed_at=datetime.now(timezone.utc),
            )
        )

        # Verify all projections
        # Check extraction process
        process_result = await db_session.execute(
            text("SELECT * FROM extraction_processes WHERE page_id = :page_id"),
            {"page_id": test_scraped_page},
        )
        process_row = process_result.mappings().fetchone()
        assert process_row["status"] == "completed"
        assert process_row["entity_count"] == 2
        assert process_row["relationship_count"] == 1

        # Check entities
        entity_result = await db_session.execute(
            text("""
                SELECT COUNT(*) as cnt
                FROM extracted_entities
                WHERE source_page_id = :page_id AND tenant_id = :tenant_id
            """),
            {"page_id": test_scraped_page, "tenant_id": test_tenant},
        )
        entity_count = entity_result.scalar()
        assert entity_count == 2

        # Check relationship
        rel_result = await db_session.execute(
            text("SELECT * FROM entity_relationships WHERE id = :id"),
            {"id": relationship_id},
        )
        rel_row = rel_result.mappings().fetchone()
        assert rel_row is not None
        assert rel_row["relationship_type"] == "CALLS"
