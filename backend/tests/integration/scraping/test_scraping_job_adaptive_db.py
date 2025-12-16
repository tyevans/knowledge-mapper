"""
Integration tests for ScrapingJob adaptive extraction columns in database.

These tests verify that the adaptive extraction columns work correctly
when persisted to and retrieved from the database.

Requires: Running PostgreSQL database with migration applied.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scraping_job import ScrapingJob, JobStatus, JobStage
from app.models.tenant import Tenant


@pytest.mark.integration
class TestScrapingJobAdaptiveColumnsDB:
    """Integration tests for adaptive extraction database operations."""

    async def test_create_legacy_job_persists_correctly(
        self, db_session: AsyncSession, test_tenant: Tenant
    ):
        """Test that a legacy job persists all defaults correctly."""
        job = ScrapingJob(
            tenant_id=test_tenant.id,
            created_by_user_id="test-user-integration",
            name="Legacy Integration Test Job",
            start_url="https://example.com",
            extraction_strategy="legacy",
        )
        db_session.add(job)
        await db_session.commit()

        # Query back the job
        result = await db_session.get(ScrapingJob, job.id)

        assert result is not None
        assert result.extraction_strategy == "legacy"
        assert result.content_domain is None
        assert result.classification_confidence is None
        assert result.inferred_schema is None
        assert result.classification_sample_size == 1
        assert result.uses_adaptive_extraction is False
        assert result.is_domain_resolved is True

    async def test_create_auto_detect_job_persists_correctly(
        self, db_session: AsyncSession, test_tenant: Tenant
    ):
        """Test that an auto_detect job persists correctly."""
        job = ScrapingJob(
            tenant_id=test_tenant.id,
            created_by_user_id="test-user-integration",
            name="Auto Detect Integration Test Job",
            start_url="https://literature-site.com",
            extraction_strategy="auto_detect",
            classification_sample_size=3,
        )
        db_session.add(job)
        await db_session.commit()

        # Query back the job
        result = await db_session.get(ScrapingJob, job.id)

        assert result is not None
        assert result.extraction_strategy == "auto_detect"
        assert result.content_domain is None
        assert result.classification_confidence is None
        assert result.classification_sample_size == 3
        assert result.uses_adaptive_extraction is True
        assert result.needs_classification is True
        assert result.is_domain_resolved is False

    async def test_create_manual_job_persists_correctly(
        self, db_session: AsyncSession, test_tenant: Tenant
    ):
        """Test that a manual job with domain persists correctly."""
        job = ScrapingJob(
            tenant_id=test_tenant.id,
            created_by_user_id="test-user-integration",
            name="Manual Integration Test Job",
            start_url="https://fiction-library.com",
            extraction_strategy="manual",
            content_domain="literature_fiction",
            inferred_schema={
                "domain_id": "literature_fiction",
                "version": "1.0.0",
                "entity_types": ["character", "location", "theme"],
            },
        )
        db_session.add(job)
        await db_session.commit()

        # Query back the job
        result = await db_session.get(ScrapingJob, job.id)

        assert result is not None
        assert result.extraction_strategy == "manual"
        assert result.content_domain == "literature_fiction"
        assert result.inferred_schema is not None
        assert result.inferred_schema["domain_id"] == "literature_fiction"
        assert result.uses_adaptive_extraction is True
        assert result.is_domain_resolved is True

    async def test_update_classification_result(
        self, db_session: AsyncSession, test_tenant: Tenant
    ):
        """Test updating a job with classification results."""
        # Create job
        job = ScrapingJob(
            tenant_id=test_tenant.id,
            created_by_user_id="test-user-integration",
            name="Classification Update Test Job",
            start_url="https://books.example.com",
            extraction_strategy="auto_detect",
            classification_sample_size=2,
        )
        db_session.add(job)
        await db_session.commit()

        # Verify initial state
        assert job.needs_classification is True
        assert job.is_domain_resolved is False

        # Simulate classification completion
        job.content_domain = "literature_fiction"
        job.classification_confidence = 0.95
        job.inferred_schema = {
            "domain_id": "literature_fiction",
            "version": "1.0.0",
            "entity_types": ["character", "theme", "plot_point"],
        }
        await db_session.commit()

        # Query back and verify
        result = await db_session.get(ScrapingJob, job.id)
        assert result.content_domain == "literature_fiction"
        assert result.classification_confidence == 0.95
        assert result.needs_classification is False
        assert result.is_domain_resolved is True

    async def test_query_by_extraction_strategy(
        self, db_session: AsyncSession, test_tenant: Tenant
    ):
        """Test querying jobs by extraction strategy."""
        # Create jobs with different strategies
        jobs_data = [
            ("Legacy Job 1", "legacy", None),
            ("Auto Job 1", "auto_detect", None),
            ("Manual Job 1", "manual", "literature_fiction"),
            ("Legacy Job 2", "legacy", None),
            ("Auto Job 2", "auto_detect", None),
        ]

        for name, strategy, domain in jobs_data:
            job = ScrapingJob(
                tenant_id=test_tenant.id,
                created_by_user_id="test-user-integration",
                name=name,
                start_url="https://example.com",
                extraction_strategy=strategy,
                content_domain=domain,
            )
            db_session.add(job)

        await db_session.commit()

        # Query auto_detect jobs
        query = select(ScrapingJob).where(
            ScrapingJob.extraction_strategy == "auto_detect",
            ScrapingJob.tenant_id == test_tenant.id,
        )
        result = await db_session.execute(query)
        auto_jobs = result.scalars().all()

        # Filter by name to avoid interference from other tests
        auto_jobs = [j for j in auto_jobs if j.name.startswith("Auto Job")]
        assert len(auto_jobs) == 2

    async def test_query_by_content_domain(
        self, db_session: AsyncSession, test_tenant: Tenant
    ):
        """Test querying jobs by content domain."""
        # Create jobs with domains
        job1 = ScrapingJob(
            tenant_id=test_tenant.id,
            created_by_user_id="test-user-integration",
            name="Fiction Domain Job",
            start_url="https://example.com",
            extraction_strategy="manual",
            content_domain="literature_fiction",
        )
        job2 = ScrapingJob(
            tenant_id=test_tenant.id,
            created_by_user_id="test-user-integration",
            name="Tech Domain Job",
            start_url="https://example.com",
            extraction_strategy="manual",
            content_domain="technical_documentation",
        )
        db_session.add(job1)
        db_session.add(job2)
        await db_session.commit()

        # Query by domain
        query = select(ScrapingJob).where(
            ScrapingJob.content_domain == "literature_fiction",
            ScrapingJob.tenant_id == test_tenant.id,
        )
        result = await db_session.execute(query)
        fiction_jobs = result.scalars().all()

        # At least our created job should be there
        fiction_names = [j.name for j in fiction_jobs]
        assert "Fiction Domain Job" in fiction_names

    async def test_inferred_schema_jsonb_operations(
        self, db_session: AsyncSession, test_tenant: Tenant
    ):
        """Test JSONB operations on inferred_schema column."""
        schema = {
            "domain_id": "technical_documentation",
            "version": "1.0.0",
            "entity_types": ["function", "class", "module", "parameter"],
            "relationship_types": ["calls", "inherits", "imports"],
            "extraction_hints": {
                "min_confidence": 0.7,
                "max_entities_per_page": 50,
            },
        }

        job = ScrapingJob(
            tenant_id=test_tenant.id,
            created_by_user_id="test-user-integration",
            name="JSONB Schema Test Job",
            start_url="https://docs.example.com",
            extraction_strategy="manual",
            content_domain="technical_documentation",
            inferred_schema=schema,
        )
        db_session.add(job)
        await db_session.commit()

        # Query back and verify complex JSONB structure
        result = await db_session.get(ScrapingJob, job.id)
        assert result.inferred_schema["domain_id"] == "technical_documentation"
        assert "function" in result.inferred_schema["entity_types"]
        assert result.inferred_schema["extraction_hints"]["min_confidence"] == 0.7


@pytest.mark.integration
class TestScrapingJobCheckConstraints:
    """Tests for database check constraints on adaptive extraction columns."""

    async def test_invalid_extraction_strategy_rejected(
        self, db_session: AsyncSession, test_tenant: Tenant
    ):
        """Test that invalid extraction_strategy values are rejected by DB."""
        from sqlalchemy.exc import IntegrityError

        job = ScrapingJob(
            tenant_id=test_tenant.id,
            created_by_user_id="test-user-integration",
            name="Invalid Strategy Job",
            start_url="https://example.com",
        )
        # Directly set invalid value bypassing model validation
        job.extraction_strategy = "invalid_strategy"
        db_session.add(job)

        with pytest.raises(IntegrityError):
            await db_session.commit()
        await db_session.rollback()

    async def test_classification_sample_size_out_of_range_rejected(
        self, db_session: AsyncSession, test_tenant: Tenant
    ):
        """Test that sample_size outside 1-5 range is rejected by DB."""
        from sqlalchemy.exc import IntegrityError

        job = ScrapingJob(
            tenant_id=test_tenant.id,
            created_by_user_id="test-user-integration",
            name="Invalid Sample Size Job",
            start_url="https://example.com",
            extraction_strategy="auto_detect",
        )
        # Directly set invalid value bypassing model validation
        job.classification_sample_size = 10
        db_session.add(job)

        with pytest.raises(IntegrityError):
            await db_session.commit()
        await db_session.rollback()

    async def test_classification_confidence_out_of_range_rejected(
        self, db_session: AsyncSession, test_tenant: Tenant
    ):
        """Test that confidence outside 0.0-1.0 range is rejected by DB."""
        from sqlalchemy.exc import IntegrityError

        job = ScrapingJob(
            tenant_id=test_tenant.id,
            created_by_user_id="test-user-integration",
            name="Invalid Confidence Job",
            start_url="https://example.com",
            extraction_strategy="auto_detect",
            content_domain="literature_fiction",
        )
        # Directly set invalid value
        job.classification_confidence = 1.5
        db_session.add(job)

        with pytest.raises(IntegrityError):
            await db_session.commit()
        await db_session.rollback()
