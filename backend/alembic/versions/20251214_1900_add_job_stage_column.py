"""Add job stage column to scraping_jobs

Revision ID: r8s9t0u1v2w3
Revises: q7r8s9t0u1v2
Create Date: 2025-12-14 19:00:00.000000

Adds stage tracking to scraping jobs to show pipeline progress:
- CRAWLING: Spider is actively fetching pages
- EXTRACTING: Entity extraction in progress
- CONSOLIDATING: Entity consolidation running
- DONE: All stages complete

Also adds progress tracking columns for each stage.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "r8s9t0u1v2w3"
down_revision: Union[str, None] = "q7r8s9t0u1v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add job_stage enum and stage tracking columns to scraping_jobs."""

    # Create the job_stage enum type
    job_stage_enum = postgresql.ENUM(
        "crawling",
        "extracting",
        "consolidating",
        "done",
        name="job_stage",
        create_type=True,
    )
    job_stage_enum.create(op.get_bind(), checkfirst=True)

    # Add stage column to scraping_jobs
    op.add_column(
        "scraping_jobs",
        sa.Column(
            "stage",
            job_stage_enum,
            nullable=False,
            server_default="crawling",
            comment="Current stage within the job lifecycle",
        ),
    )

    # Add consolidation task tracking
    op.add_column(
        "scraping_jobs",
        sa.Column(
            "consolidation_task_id",
            sa.String(255),
            nullable=True,
            comment="Celery task ID for consolidation job",
        ),
    )

    # Add extraction progress tracking
    op.add_column(
        "scraping_jobs",
        sa.Column(
            "extraction_progress",
            sa.Float(),
            nullable=False,
            server_default="0.0",
            comment="Extraction progress (0.0-1.0)",
        ),
    )

    # Add consolidation progress tracking
    op.add_column(
        "scraping_jobs",
        sa.Column(
            "consolidation_progress",
            sa.Float(),
            nullable=False,
            server_default="0.0",
            comment="Consolidation progress (0.0-1.0)",
        ),
    )

    # Add pages pending extraction count
    op.add_column(
        "scraping_jobs",
        sa.Column(
            "pages_pending_extraction",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Pages awaiting entity extraction",
        ),
    )

    # Add consolidation metrics
    op.add_column(
        "scraping_jobs",
        sa.Column(
            "consolidation_candidates_found",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Number of merge candidates identified",
        ),
    )

    op.add_column(
        "scraping_jobs",
        sa.Column(
            "consolidation_auto_merged",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Number of auto-merged entity pairs",
        ),
    )

    # Create index on stage column for filtering
    op.create_index(
        "ix_scraping_jobs_stage",
        "scraping_jobs",
        ["stage"],
        unique=False,
    )

    # Update existing completed jobs to have stage='done'
    op.execute("""
        UPDATE scraping_jobs
        SET stage = 'done'
        WHERE status = 'completed'
    """)


def downgrade() -> None:
    """Remove job stage tracking columns from scraping_jobs."""

    # Drop index
    op.drop_index("ix_scraping_jobs_stage", table_name="scraping_jobs")

    # Drop columns
    op.drop_column("scraping_jobs", "consolidation_auto_merged")
    op.drop_column("scraping_jobs", "consolidation_candidates_found")
    op.drop_column("scraping_jobs", "pages_pending_extraction")
    op.drop_column("scraping_jobs", "consolidation_progress")
    op.drop_column("scraping_jobs", "extraction_progress")
    op.drop_column("scraping_jobs", "consolidation_task_id")
    op.drop_column("scraping_jobs", "stage")

    # Drop enum type
    op.execute("DROP TYPE IF EXISTS job_stage")
