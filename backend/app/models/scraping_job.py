"""
Scraping job model for web scraping orchestration.

This module defines the ScrapingJob model, which represents a web scraping job
configuration and its execution status. Jobs are tenant-isolated via RLS policies.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum as SQLEnum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.scraped_page import ScrapedPage
    from app.models.tenant import Tenant


class JobStatus(str, enum.Enum):
    """Enumeration of scraping job states."""

    PENDING = "pending"  # Created but not started
    QUEUED = "queued"  # Submitted to Celery queue
    RUNNING = "running"  # Spider is actively crawling
    PAUSED = "paused"  # Temporarily stopped (can resume)
    COMPLETED = "completed"  # Finished successfully
    FAILED = "failed"  # Terminated with error
    CANCELLED = "cancelled"  # User-cancelled


class ScrapingJob(Base):
    """
    Represents a web scraping job configuration and status.

    Each job belongs to a tenant and contains configuration for how to crawl
    a website, including start URL, depth, speed limits, and more. The job
    tracks progress and can be started, stopped, or cancelled.

    Attributes:
        id: UUID primary key for security
        tenant_id: Foreign key to tenant (RLS enforced)
        created_by_user_id: User who created the job
        name: Human-readable job name
        start_url: URL to begin crawling from
        allowed_domains: List of domains to stay within
        url_patterns: Regex patterns for URLs to include
        excluded_patterns: Regex patterns for URLs to exclude
        crawl_depth: Maximum link depth to follow
        max_pages: Maximum pages to scrape
        crawl_speed: Requests per second limit
        respect_robots_txt: Honor robots.txt rules
        custom_settings: Additional Scrapy settings
        status: Current job status
        celery_task_id: Celery task ID for control
        pages_crawled: Number of pages successfully scraped
        entities_extracted: Number of entities found
        errors_count: Number of errors encountered
        started_at: When crawling began
        completed_at: When crawling finished
        error_message: Last error message if failed
        created_at: Timestamp of creation (inherited)
        updated_at: Timestamp of last update (inherited)
    """

    __tablename__ = "scraping_jobs"

    # Primary key - UUID for security
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        insert_default=uuid.uuid4,
        index=True,
        comment="UUID primary key for security",
    )

    # Tenant isolation (RLS enforced)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Tenant this job belongs to (RLS enforced)",
    )

    # Job ownership
    created_by_user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="User ID who created this job",
    )

    # Job configuration
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Human-readable job name",
    )

    start_url: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
        comment="URL to begin crawling from",
    )

    allowed_domains: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        insert_default=list,
        comment="List of domains to stay within",
    )

    url_patterns: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Regex patterns for URLs to include",
    )

    excluded_patterns: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Regex patterns for URLs to exclude",
    )

    crawl_depth: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=2,
        insert_default=2,
        comment="Maximum link depth to follow",
    )

    max_pages: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
        insert_default=100,
        comment="Maximum number of pages to scrape",
    )

    crawl_speed: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=1.0,
        insert_default=1.0,
        comment="Requests per second limit",
    )

    respect_robots_txt: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        insert_default=True,
        comment="Honor robots.txt rules",
    )

    use_llm_extraction: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        insert_default=True,
        comment="Use LLM for semantic entity extraction",
    )

    custom_settings: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        insert_default=dict,
        comment="Additional Scrapy settings",
    )

    # Status tracking
    status: Mapped[JobStatus] = mapped_column(
        SQLEnum(
            JobStatus,
            name="job_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=JobStatus.PENDING,
        insert_default=JobStatus.PENDING,
        index=True,
        comment="Current job status",
    )

    celery_task_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Celery task ID for job control",
    )

    # Progress metrics
    pages_crawled: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        insert_default=0,
        comment="Number of pages successfully scraped",
    )

    entities_extracted: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        insert_default=0,
        comment="Number of entities extracted",
    )

    errors_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        insert_default=0,
        comment="Number of errors encountered",
    )

    # Timing
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When crawling began",
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When crawling finished",
    )

    # Error handling
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Last error message if failed",
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        doc="Tenant this job belongs to",
    )

    scraped_pages: Mapped[list["ScrapedPage"]] = relationship(
        "ScrapedPage",
        back_populates="job",
        cascade="all, delete-orphan",
        doc="Pages scraped by this job",
    )

    def __init__(self, **kwargs):
        """Initialize job with default values for optional fields."""
        if "id" not in kwargs:
            kwargs["id"] = uuid.uuid4()
        if "allowed_domains" not in kwargs:
            kwargs["allowed_domains"] = []
        if "custom_settings" not in kwargs:
            kwargs["custom_settings"] = {}
        if "status" not in kwargs:
            kwargs["status"] = JobStatus.PENDING
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        """Return string representation of the job."""
        return f"<ScrapingJob {self.id} '{self.name}' ({self.status.value})>"

    @property
    def is_active(self) -> bool:
        """Check if job is currently active (queued or running)."""
        return self.status in (JobStatus.QUEUED, JobStatus.RUNNING)

    @property
    def can_start(self) -> bool:
        """Check if job can be started."""
        return self.status in (JobStatus.PENDING, JobStatus.PAUSED)

    @property
    def can_stop(self) -> bool:
        """Check if job can be stopped."""
        return self.status in (JobStatus.QUEUED, JobStatus.RUNNING)
