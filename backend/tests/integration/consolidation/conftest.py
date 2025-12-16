"""
Pytest configuration and fixtures for consolidation integration tests.

Provides fixtures for:
- Database session management with tenant context
- Test entities with known similarity relationships
- Multi-tenant test data for isolation verification
- Various entity types (Person, Organization, Concept, etc.)
"""

import hashlib
import os
import pytest
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.models import (
    ExtractedEntity,
    EntityType,
    ExtractionMethod,
    ScrapedPage,
    ScrapingJob,
    JobStatus,
    Tenant,
)


# Create async engine using migration user (BYPASSRLS)
# This is needed for test setup/teardown to bypass RLS policies
_MIGRATION_USER_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://knowledge_mapper_migration_user:migration_password_dev@postgres:5432/knowledge_mapper_db"
)

_test_engine = create_async_engine(
    _MIGRATION_USER_DB_URL,
    pool_size=5,
    max_overflow=5,
    echo=False,
)

TestAsyncSessionLocal = async_sessionmaker(
    _test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# Register custom markers
def pytest_configure(config):
    """Register custom markers for consolidation integration tests."""
    config.addinivalue_line(
        "markers",
        "integration: marks tests as integration tests (require database/services)"
    )


@pytest.fixture(scope="session")
def anyio_backend():
    """Configure anyio backend for async tests."""
    return "asyncio"


# ---------------------------------------------------------------------------
# Database Session Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_session():
    """
    Create a test database session with BYPASSRLS for setup/teardown.

    This fixture provides a session that bypasses RLS for test setup,
    using the migration user which has BYPASSRLS permission.
    Ensures cleanup of all test data after each test.
    """
    async with TestAsyncSessionLocal() as session:
        # Track created tenant IDs for cleanup
        created_tenant_ids = []
        session.info["created_tenant_ids"] = created_tenant_ids

        yield session

        # Clean up test data in correct order (respect foreign keys)
        if created_tenant_ids:
            # Delete merge-related data first
            await session.execute(
                text("DELETE FROM merge_history WHERE tenant_id = ANY(:ids)"),
                {"ids": created_tenant_ids},
            )
            await session.execute(
                text("DELETE FROM entity_aliases WHERE tenant_id = ANY(:ids)"),
                {"ids": created_tenant_ids},
            )
            await session.execute(
                text("DELETE FROM merge_review_queue WHERE tenant_id = ANY(:ids)"),
                {"ids": created_tenant_ids},
            )
            # Delete entity relationships (they reference entities)
            await session.execute(
                text("DELETE FROM entity_relationships WHERE tenant_id = ANY(:ids)"),
                {"ids": created_tenant_ids},
            )
            # Delete entities (they reference scraped_pages)
            await session.execute(
                text("DELETE FROM extracted_entities WHERE tenant_id = ANY(:ids)"),
                {"ids": created_tenant_ids},
            )
            # Delete pages (they reference scraping_jobs)
            await session.execute(
                text("DELETE FROM scraped_pages WHERE tenant_id = ANY(:ids)"),
                {"ids": created_tenant_ids},
            )
            # Delete jobs
            await session.execute(
                text("DELETE FROM scraping_jobs WHERE tenant_id = ANY(:ids)"),
                {"ids": created_tenant_ids},
            )
            # Delete tenants last
            await session.execute(
                text("DELETE FROM tenants WHERE id = ANY(:ids)"),
                {"ids": created_tenant_ids},
            )
            await session.commit()


# ---------------------------------------------------------------------------
# Tenant Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def tenant_acme(db_session: AsyncSession):
    """Create ACME Corp tenant for testing."""
    unique_id = str(uuid4())[:8]
    tenant = Tenant(
        slug=f"acme-corp-{unique_id}",
        name="ACME Corporation",
        is_active=True,
    )
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)
    db_session.info["created_tenant_ids"].append(str(tenant.id))
    return tenant


@pytest.fixture
async def tenant_globex(db_session: AsyncSession):
    """Create Globex tenant for testing."""
    unique_id = str(uuid4())[:8]
    tenant = Tenant(
        slug=f"globex-inc-{unique_id}",
        name="Globex Inc",
        is_active=True,
    )
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)
    db_session.info["created_tenant_ids"].append(str(tenant.id))
    return tenant


# ---------------------------------------------------------------------------
# Scraping Job and Page Fixtures
# ---------------------------------------------------------------------------


def _create_content_hash(content: str) -> str:
    """Create SHA-256 hash for content deduplication."""
    return hashlib.sha256(content.encode()).hexdigest()


@pytest.fixture
async def scraping_job_acme(db_session: AsyncSession, tenant_acme: Tenant):
    """Create a scraping job for ACME Corp."""
    job = ScrapingJob(
        tenant_id=tenant_acme.id,
        created_by_user_id="test-user-acme",
        name="Test Crawl",
        start_url="https://example.com",
        allowed_domains=["example.com"],
        status=JobStatus.COMPLETED,
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    return job


@pytest.fixture
async def scraping_job_globex(db_session: AsyncSession, tenant_globex: Tenant):
    """Create a scraping job for Globex."""
    job = ScrapingJob(
        tenant_id=tenant_globex.id,
        created_by_user_id="test-user-globex",
        name="Test Crawl",
        start_url="https://globex.example.com",
        allowed_domains=["globex.example.com"],
        status=JobStatus.COMPLETED,
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    return job


@pytest.fixture
async def scraped_page_acme(
    db_session: AsyncSession,
    tenant_acme: Tenant,
    scraping_job_acme: ScrapingJob,
):
    """Create a scraped page for ACME Corp."""
    html = "<html><body>Test content</body></html>"
    page = ScrapedPage(
        tenant_id=tenant_acme.id,
        job_id=scraping_job_acme.id,
        url="https://example.com/page1",
        content_hash=_create_content_hash(html),
        html_content=html,
        text_content="Test content",
        title="Test Page",
        http_status=200,
        crawled_at=datetime.now(timezone.utc),
    )
    db_session.add(page)
    await db_session.commit()
    await db_session.refresh(page)
    return page


@pytest.fixture
async def scraped_page_acme_2(
    db_session: AsyncSession,
    tenant_acme: Tenant,
    scraping_job_acme: ScrapingJob,
):
    """Create a second scraped page for ACME Corp."""
    html = "<html><body>Another page</body></html>"
    page = ScrapedPage(
        tenant_id=tenant_acme.id,
        job_id=scraping_job_acme.id,
        url="https://example.com/page2",
        content_hash=_create_content_hash(html),
        html_content=html,
        text_content="Another page content",
        title="Another Page",
        http_status=200,
        crawled_at=datetime.now(timezone.utc),
    )
    db_session.add(page)
    await db_session.commit()
    await db_session.refresh(page)
    return page


@pytest.fixture
async def scraped_page_globex(
    db_session: AsyncSession,
    tenant_globex: Tenant,
    scraping_job_globex: ScrapingJob,
):
    """Create a scraped page for Globex."""
    html = "<html><body>Globex content</body></html>"
    page = ScrapedPage(
        tenant_id=tenant_globex.id,
        job_id=scraping_job_globex.id,
        url="https://globex.example.com/page1",
        content_hash=_create_content_hash(html),
        html_content=html,
        text_content="Globex content",
        title="Globex Page",
        http_status=200,
        crawled_at=datetime.now(timezone.utc),
    )
    db_session.add(page)
    await db_session.commit()
    await db_session.refresh(page)
    return page


# ---------------------------------------------------------------------------
# Entity Factory Functions
# ---------------------------------------------------------------------------


def create_entity(
    tenant_id,
    source_page_id,
    name: str,
    entity_type: EntityType | str = EntityType.CONCEPT,
    extraction_method: ExtractionMethod = ExtractionMethod.LLM_OLLAMA,
    confidence_score: float = 0.9,
    properties: dict | None = None,
    is_canonical: bool = True,
) -> ExtractedEntity:
    """Factory function to create test entities.

    Args:
        entity_type: Can be an EntityType enum (for legacy types) or string
                    (for domain-specific types like 'character', 'theme').
    """
    # Convert enum to string value if needed
    entity_type_str = entity_type.value if isinstance(entity_type, EntityType) else entity_type
    return ExtractedEntity(
        tenant_id=tenant_id,
        source_page_id=source_page_id,
        name=name,
        entity_type=entity_type_str,
        extraction_method=extraction_method,
        confidence_score=confidence_score,
        properties=properties or {},
        is_canonical=is_canonical,
    )


# ---------------------------------------------------------------------------
# Entity Fixtures - Person Entities with Known Similarity
# ---------------------------------------------------------------------------


@pytest.fixture
async def person_entities_acme(
    db_session: AsyncSession,
    tenant_acme: Tenant,
    scraped_page_acme: ScrapedPage,
):
    """
    Create person entities with known similarity relationships.

    Returns a dict with entity names as keys for easy testing:
    - "john_smith": Canonical reference
    - "john_smith_jr": Should match (high phonetic similarity)
    - "john_smyth": Should match (phonetic similarity)
    - "jon_smith": Should match (high string similarity, phonetic match)
    - "jane_doe": Should NOT match (different person)
    - "j_smith": Ambiguous (might match)
    """
    entities = {
        "john_smith": create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "John Smith",
            EntityType.PERSON,
            properties={"role": "Engineer"},
        ),
        "john_smith_jr": create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "John Smith Jr.",
            EntityType.PERSON,
            properties={"role": "Engineer"},
        ),
        "john_smyth": create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "John Smyth",
            EntityType.PERSON,
            properties={"role": "Developer"},
        ),
        "jon_smith": create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "Jon Smith",
            EntityType.PERSON,
            properties={"role": "Developer"},
        ),
        "jane_doe": create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "Jane Doe",
            EntityType.PERSON,
            properties={"role": "Manager"},
        ),
        "j_smith": create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "J. Smith",
            EntityType.PERSON,
            properties={"role": "Unknown"},
        ),
    }

    for entity in entities.values():
        db_session.add(entity)

    await db_session.commit()

    for entity in entities.values():
        await db_session.refresh(entity)

    return entities


# ---------------------------------------------------------------------------
# Entity Fixtures - Organization Entities
# ---------------------------------------------------------------------------


@pytest.fixture
async def org_entities_acme(
    db_session: AsyncSession,
    tenant_acme: Tenant,
    scraped_page_acme: ScrapedPage,
):
    """
    Create organization entities with known similarity relationships.

    Returns a dict with entity names as keys:
    - "acme_corp": Full name
    - "acme_corporation": Variation (should match)
    - "acme_inc": Different suffix (might match)
    - "google_inc": Different org (should NOT match)
    """
    entities = {
        "acme_corp": create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "ACME Corp",
            EntityType.ORGANIZATION,
            properties={"industry": "Manufacturing"},
        ),
        "acme_corporation": create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "ACME Corporation",
            EntityType.ORGANIZATION,
            properties={"industry": "Manufacturing"},
        ),
        "acme_inc": create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "ACME Inc",
            EntityType.ORGANIZATION,
            properties={"industry": "Manufacturing"},
        ),
        "google_inc": create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "Google Inc",
            EntityType.ORGANIZATION,
            properties={"industry": "Technology"},
        ),
    }

    for entity in entities.values():
        db_session.add(entity)

    await db_session.commit()

    for entity in entities.values():
        await db_session.refresh(entity)

    return entities


# ---------------------------------------------------------------------------
# Entity Fixtures - Technical Entities (Classes, Functions)
# ---------------------------------------------------------------------------


@pytest.fixture
async def technical_entities_acme(
    db_session: AsyncSession,
    tenant_acme: Tenant,
    scraped_page_acme: ScrapedPage,
):
    """
    Create technical entities with known similarity relationships.

    Returns a dict with entity names as keys:
    - "domain_event": Canonical class name
    - "DomainEvent": CamelCase variation (should match)
    - "domain_event_base": Extended name (might match)
    - "base_event": Different class (should NOT match)
    """
    entities = {
        "domain_event": create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "domain_event",
            EntityType.CLASS,
            properties={"module": "eventsourcing"},
        ),
        "DomainEvent": create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "DomainEvent",
            EntityType.CLASS,
            properties={"module": "eventsourcing"},
        ),
        "domain_event_base": create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "domain_event_base",
            EntityType.CLASS,
            properties={"module": "eventsourcing.base"},
        ),
        "base_event": create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "base_event",
            EntityType.CLASS,
            properties={"module": "events"},
        ),
    }

    for entity in entities.values():
        db_session.add(entity)

    await db_session.commit()

    for entity in entities.values():
        await db_session.refresh(entity)

    return entities


# ---------------------------------------------------------------------------
# Entity Fixtures - Location Entities
# ---------------------------------------------------------------------------


@pytest.fixture
async def location_entities_acme(
    db_session: AsyncSession,
    tenant_acme: Tenant,
    scraped_page_acme: ScrapedPage,
):
    """
    Create location entities with known similarity relationships.

    Returns a dict with entity names as keys:
    - "new_york": Full name
    - "new_york_city": Extended name (should match)
    - "nyc": Abbreviation (might match with context)
    - "los_angeles": Different city (should NOT match)
    """
    entities = {
        "new_york": create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "New York",
            EntityType.LOCATION,
            properties={"country": "USA", "type": "city"},
        ),
        "new_york_city": create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "New York City",
            EntityType.LOCATION,
            properties={"country": "USA", "type": "city"},
        ),
        "nyc": create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "NYC",
            EntityType.LOCATION,
            properties={"country": "USA", "type": "city"},
        ),
        "los_angeles": create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "Los Angeles",
            EntityType.LOCATION,
            properties={"country": "USA", "type": "city"},
        ),
    }

    for entity in entities.values():
        db_session.add(entity)

    await db_session.commit()

    for entity in entities.values():
        await db_session.refresh(entity)

    return entities


# ---------------------------------------------------------------------------
# Entity Fixtures - Mixed Types on Same Page
# ---------------------------------------------------------------------------


@pytest.fixture
async def mixed_entities_same_page(
    db_session: AsyncSession,
    tenant_acme: Tenant,
    scraped_page_acme: ScrapedPage,
):
    """
    Create entities of different types on the same page.

    Tests contextual signals like same_page and type_match.
    """
    entities = {
        "event_sourcing_concept": create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "Event Sourcing",
            EntityType.CONCEPT,
            properties={"category": "pattern"},
        ),
        "event_sourcing_pattern": create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "Event Sourcing Pattern",
            EntityType.PATTERN,
            properties={"category": "architecture"},
        ),
        "cqrs_concept": create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "CQRS",
            EntityType.CONCEPT,
            properties={"category": "pattern"},
        ),
        "ddd_concept": create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "Domain Driven Design",
            EntityType.CONCEPT,
            properties={"category": "methodology"},
        ),
    }

    for entity in entities.values():
        db_session.add(entity)

    await db_session.commit()

    for entity in entities.values():
        await db_session.refresh(entity)

    return entities


# ---------------------------------------------------------------------------
# Entity Fixtures - Globex Tenant (for isolation testing)
# ---------------------------------------------------------------------------


@pytest.fixture
async def person_entities_globex(
    db_session: AsyncSession,
    tenant_globex: Tenant,
    scraped_page_globex: ScrapedPage,
):
    """
    Create person entities for Globex tenant.

    Used to verify tenant isolation - ACME entities should NOT
    see these as candidates.
    """
    entities = {
        "john_smith_globex": create_entity(
            tenant_globex.id,
            scraped_page_globex.id,
            "John Smith",  # Same name as ACME entity
            EntityType.PERSON,
            properties={"role": "CEO"},
        ),
        "alice_jones_globex": create_entity(
            tenant_globex.id,
            scraped_page_globex.id,
            "Alice Jones",
            EntityType.PERSON,
            properties={"role": "CTO"},
        ),
    }

    for entity in entities.values():
        db_session.add(entity)

    await db_session.commit()

    for entity in entities.values():
        await db_session.refresh(entity)

    return entities


# ---------------------------------------------------------------------------
# Entity Fixtures - Large Dataset for Performance Testing
# ---------------------------------------------------------------------------


@pytest.fixture
async def large_entity_dataset(
    db_session: AsyncSession,
    tenant_acme: Tenant,
    scraped_page_acme: ScrapedPage,
):
    """
    Create a larger dataset for performance testing.

    Creates 100 entities with various names to test blocking efficiency.
    """
    base_names = [
        "Database",
        "Repository",
        "Service",
        "Controller",
        "Handler",
        "Factory",
        "Builder",
        "Manager",
        "Provider",
        "Client",
    ]

    suffixes = [
        "Interface",
        "Implementation",
        "Abstract",
        "Base",
        "Default",
        "Custom",
        "Simple",
        "Complex",
        "Async",
        "Sync",
    ]

    entities = []
    for base in base_names:
        for suffix in suffixes:
            name = f"{base}{suffix}"
            entity = create_entity(
                tenant_acme.id,
                scraped_page_acme.id,
                name,
                EntityType.CLASS,
                properties={"category": base.lower()},
            )
            entities.append(entity)
            db_session.add(entity)

    await db_session.commit()

    for entity in entities:
        await db_session.refresh(entity)

    return entities


# ---------------------------------------------------------------------------
# Entity Fixtures - Entities Across Different Pages
# ---------------------------------------------------------------------------


@pytest.fixture
async def entities_different_pages(
    db_session: AsyncSession,
    tenant_acme: Tenant,
    scraped_page_acme: ScrapedPage,
    scraped_page_acme_2: ScrapedPage,
):
    """
    Create similar entities on different pages.

    Tests that same_page contextual signal works correctly.
    """
    entities = {
        "api_client_page1": create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "APIClient",
            EntityType.CLASS,
            properties={"module": "api"},
        ),
        "api_client_page2": create_entity(
            tenant_acme.id,
            scraped_page_acme_2.id,
            "API Client",  # Slightly different name
            EntityType.CLASS,
            properties={"module": "api"},
        ),
        "http_client_page1": create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "HTTPClient",
            EntityType.CLASS,
            properties={"module": "http"},
        ),
        "http_client_page2": create_entity(
            tenant_acme.id,
            scraped_page_acme_2.id,
            "HttpClient",  # Different casing
            EntityType.CLASS,
            properties={"module": "http"},
        ),
    }

    for entity in entities.values():
        db_session.add(entity)

    await db_session.commit()

    for entity in entities.values():
        await db_session.refresh(entity)

    return entities
