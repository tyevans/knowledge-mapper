"""Add extraction_provider_id to scraping_jobs.

Revision ID: t0u1v2w3x4y5
Revises: s9t0u1v2w3x4
Create Date: 2025-12-14 21:00:00.000000

This migration adds:
- extraction_provider_id FK to scraping_jobs for per-job provider selection
- Index on extraction_provider_id for efficient joins
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = "t0u1v2w3x4y5"
down_revision: Union[str, None] = "s9t0u1v2w3x4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add extraction_provider_id column to scraping_jobs."""

    # Add extraction_provider_id column
    op.add_column(
        "scraping_jobs",
        sa.Column(
            "extraction_provider_id",
            UUID(as_uuid=True),
            sa.ForeignKey("extraction_providers.id", ondelete="SET NULL"),
            nullable=True,
            comment="Provider to use for extraction (null = use default/global)",
        ),
    )

    # Create index for efficient joins
    op.create_index(
        "ix_scraping_jobs_extraction_provider",
        "scraping_jobs",
        ["extraction_provider_id"],
    )


def downgrade() -> None:
    """Remove extraction_provider_id column from scraping_jobs."""

    # Drop index
    op.drop_index("ix_scraping_jobs_extraction_provider", table_name="scraping_jobs")

    # Drop column
    op.drop_column("scraping_jobs", "extraction_provider_id")
