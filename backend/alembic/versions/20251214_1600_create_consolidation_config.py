"""Create consolidation_config table

Revision ID: o5p6q7r8s9t0
Revises: n4o5p6q7r8s9
Create Date: 2025-12-14 16:00:00.000000

Creates the consolidation_config table for per-tenant consolidation settings.
Each tenant can customize thresholds, feature weights, and operational settings.

Includes check constraints to ensure valid threshold ranges and ordering.
"""

from typing import Sequence, Union
import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "o5p6q7r8s9t0"
down_revision: Union[str, None] = "n4o5p6q7r8s9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Default feature weights
DEFAULT_WEIGHTS = {
    "jaro_winkler": 0.3,
    "normalized_exact": 0.4,
    "type_match": 0.2,
    "same_page_bonus": 0.1,
    "embedding_cosine": 0.5,
    "graph_neighborhood": 0.3,
    "fast_composite": 0.2,
}


def upgrade() -> None:
    """Create consolidation_config table with constraints."""

    # Create consolidation_config table
    op.create_table(
        "consolidation_config",
        # Primary key is tenant_id (one config per tenant)
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            comment="Tenant this configuration belongs to",
        ),
        # Confidence thresholds
        sa.Column(
            "auto_merge_threshold",
            sa.Float(),
            nullable=False,
            server_default="0.90",
            comment="Confidence threshold for automatic merging (0.0-1.0)",
        ),
        sa.Column(
            "review_threshold",
            sa.Float(),
            nullable=False,
            server_default="0.50",
            comment="Confidence threshold for queueing human review (0.0-1.0)",
        ),
        # Operational settings
        sa.Column(
            "max_block_size",
            sa.Integer(),
            nullable=False,
            server_default="500",
            comment="Maximum entities per blocking group",
        ),
        # Feature toggles
        sa.Column(
            "enable_embedding_similarity",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="Whether to compute embedding similarity",
        ),
        sa.Column(
            "enable_graph_similarity",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="Whether to compute graph neighborhood similarity",
        ),
        sa.Column(
            "enable_auto_consolidation",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="Whether to run consolidation on new entity extraction",
        ),
        # Model configuration
        sa.Column(
            "embedding_model",
            sa.String(255),
            nullable=False,
            server_default="'bge-m3'",
            comment="Embedding model to use for semantic similarity",
        ),
        # Feature weights
        sa.Column(
            "feature_weights",
            postgresql.JSONB(),
            nullable=False,
            server_default=json.dumps(DEFAULT_WEIGHTS),
            comment="Weights for combining similarity scores",
        ),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="When config was created",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When config was last updated",
        ),
        # Foreign key
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_consolidation_config_tenant",
            ondelete="CASCADE",
        ),
    )

    # Add check constraints for valid threshold ranges
    op.execute("""
        ALTER TABLE consolidation_config
        ADD CONSTRAINT chk_auto_merge_threshold
        CHECK (auto_merge_threshold >= 0.0 AND auto_merge_threshold <= 1.0)
    """)

    op.execute("""
        ALTER TABLE consolidation_config
        ADD CONSTRAINT chk_review_threshold
        CHECK (review_threshold >= 0.0 AND review_threshold <= 1.0)
    """)

    # Review threshold must be less than auto_merge threshold
    op.execute("""
        ALTER TABLE consolidation_config
        ADD CONSTRAINT chk_review_less_than_auto
        CHECK (review_threshold < auto_merge_threshold)
    """)

    # Max block size must be positive and reasonable
    op.execute("""
        ALTER TABLE consolidation_config
        ADD CONSTRAINT chk_max_block_size
        CHECK (max_block_size > 0 AND max_block_size <= 10000)
    """)

    # Grant permissions (no RLS needed - primary key is tenant_id)
    # Queries will be filtered by tenant_id in application logic
    op.execute("""
        GRANT SELECT, INSERT, UPDATE ON consolidation_config
        TO knowledge_mapper_app_user
    """)


def downgrade() -> None:
    """Drop consolidation_config table."""
    op.drop_table("consolidation_config")
