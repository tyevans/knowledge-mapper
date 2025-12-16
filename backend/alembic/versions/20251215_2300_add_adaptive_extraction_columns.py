"""Add adaptive extraction columns to scraping_jobs.

Revision ID: a1b2c3d4e5f6
Revises: u1v2w3x4y5z6
Create Date: 2025-12-15

Adds columns for the Adaptive Extraction Strategy feature:
- extraction_strategy: The extraction approach (legacy, auto_detect, manual)
- content_domain: The detected or manually selected domain ID
- classification_confidence: Confidence score from content classification
- inferred_schema: Snapshot of domain schema used for extraction
- classification_sample_size: Number of pages to sample for classification

These columns enable domain-specific extraction by storing:
1. How extraction strategy was determined (legacy, auto-detect, or manual)
2. Which domain schema applies (literature_fiction, technical_docs, etc.)
3. Confidence from content classification (for auto_detect)
4. Schema snapshot for consistency during job execution

All columns are backward-compatible:
- extraction_strategy defaults to 'legacy' (existing behavior)
- All other columns are nullable with appropriate defaults
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = "v2w3x4y5z6a1"
down_revision: Union[str, None] = "u1v2w3x4y5z6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add adaptive extraction columns to scraping_jobs."""

    # extraction_strategy: The approach for entity extraction
    # Values: 'legacy' (existing LLM extraction), 'auto_detect' (classify then extract),
    #         'manual' (user-specified domain)
    op.add_column(
        "scraping_jobs",
        sa.Column(
            "extraction_strategy",
            sa.String(20),
            nullable=False,
            server_default="legacy",
            comment="Extraction strategy: legacy, auto_detect, or manual",
        ),
    )

    # content_domain: The detected or selected domain ID
    # NULL for legacy strategy, populated for auto_detect/manual
    op.add_column(
        "scraping_jobs",
        sa.Column(
            "content_domain",
            sa.String(50),
            nullable=True,
            comment="Content domain ID (e.g., literature_fiction)",
        ),
    )

    # classification_confidence: Confidence from auto-detection
    # Only populated for auto_detect strategy
    op.add_column(
        "scraping_jobs",
        sa.Column(
            "classification_confidence",
            sa.Float(),
            nullable=True,
            comment="Classification confidence score (0.0-1.0)",
        ),
    )

    # inferred_schema: Snapshot of domain schema at job creation
    # Stores the complete schema used for extraction to ensure consistency
    op.add_column(
        "scraping_jobs",
        sa.Column(
            "inferred_schema",
            JSONB(),
            nullable=True,
            comment="Snapshot of domain schema used for extraction",
        ),
    )

    # classification_sample_size: Pages to sample for classification
    # Only relevant for auto_detect, defaults to 1
    op.add_column(
        "scraping_jobs",
        sa.Column(
            "classification_sample_size",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="Number of pages to sample for classification (1-5)",
        ),
    )

    # Add index on extraction_strategy for filtering jobs by strategy
    op.create_index(
        "ix_scraping_jobs_extraction_strategy",
        "scraping_jobs",
        ["extraction_strategy"],
    )

    # Add index on content_domain for analytics and filtering
    op.create_index(
        "ix_scraping_jobs_content_domain",
        "scraping_jobs",
        ["content_domain"],
    )

    # Add check constraint for extraction_strategy values
    op.create_check_constraint(
        "ck_scraping_jobs_extraction_strategy",
        "scraping_jobs",
        "extraction_strategy IN ('legacy', 'auto_detect', 'manual')",
    )

    # Add check constraint for classification_sample_size range (1-5)
    op.create_check_constraint(
        "ck_scraping_jobs_classification_sample_size",
        "scraping_jobs",
        "classification_sample_size >= 1 AND classification_sample_size <= 5",
    )

    # Add check constraint for classification_confidence range (0.0-1.0)
    op.create_check_constraint(
        "ck_scraping_jobs_classification_confidence",
        "scraping_jobs",
        "classification_confidence IS NULL OR (classification_confidence >= 0.0 AND classification_confidence <= 1.0)",
    )


def downgrade() -> None:
    """Remove adaptive extraction columns from scraping_jobs."""

    # Drop check constraints first (must be removed before columns)
    op.drop_constraint(
        "ck_scraping_jobs_classification_confidence",
        "scraping_jobs",
        type_="check",
    )
    op.drop_constraint(
        "ck_scraping_jobs_classification_sample_size",
        "scraping_jobs",
        type_="check",
    )
    op.drop_constraint(
        "ck_scraping_jobs_extraction_strategy",
        "scraping_jobs",
        type_="check",
    )

    # Drop indexes
    op.drop_index("ix_scraping_jobs_content_domain", table_name="scraping_jobs")
    op.drop_index("ix_scraping_jobs_extraction_strategy", table_name="scraping_jobs")

    # Drop columns in reverse order of creation
    op.drop_column("scraping_jobs", "classification_sample_size")
    op.drop_column("scraping_jobs", "inferred_schema")
    op.drop_column("scraping_jobs", "classification_confidence")
    op.drop_column("scraping_jobs", "content_domain")
    op.drop_column("scraping_jobs", "extraction_strategy")
