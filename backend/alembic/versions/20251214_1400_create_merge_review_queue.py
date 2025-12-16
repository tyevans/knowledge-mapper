"""Create merge_review_queue table

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7
Create Date: 2025-12-14 14:00:00.000000

Creates the merge_review_queue table for human-in-the-loop entity consolidation.
Review items are created for merge candidates with medium confidence scores
(50-89%) that require human judgment before merging.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "m3n4o5p6q7r8"
down_revision: Union[str, None] = "l2m3n4o5p6q7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create merge_review_queue table with RLS and indexes."""

    # Create enum type for review status (use raw SQL with IF NOT EXISTS)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'merge_review_status') THEN
                CREATE TYPE merge_review_status AS ENUM ('pending', 'approved', 'rejected', 'deferred', 'expired');
            END IF;
        END$$;
    """)

    # Create merge_review_queue table
    op.create_table(
        "merge_review_queue",
        # Primary key
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            comment="UUID primary key",
        ),
        # Tenant isolation
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Tenant this review item belongs to (RLS enforced)",
        ),
        # Entity pair
        sa.Column(
            "entity_a_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="First entity in the candidate pair",
        ),
        sa.Column(
            "entity_b_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Second entity in the candidate pair",
        ),
        # Similarity scoring
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
            comment="Combined similarity confidence score (0.0-1.0)",
        ),
        sa.Column(
            "review_priority",
            sa.Float(),
            nullable=False,
            comment="Priority for queue ordering (1.0 = highest uncertainty)",
        ),
        sa.Column(
            "similarity_scores",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
            comment="Detailed similarity score breakdown by method",
        ),
        # Review status
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending",
                "approved",
                "rejected",
                "deferred",
                "expired",
                name="merge_review_status",
                create_type=False,  # Already created above
            ),
            nullable=False,
            server_default="pending",
            comment="Current review status",
        ),
        # Reviewer information
        sa.Column(
            "reviewed_by",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="User who reviewed this item",
        ),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the review occurred",
        ),
        sa.Column(
            "reviewer_notes",
            sa.Text(),
            nullable=True,
            comment="Optional notes from the reviewer",
        ),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="When the item was queued",
        ),
        # Foreign keys
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_merge_review_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["entity_a_id"],
            ["extracted_entities.id"],
            name="fk_merge_review_entity_a",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["entity_b_id"],
            ["extracted_entities.id"],
            name="fk_merge_review_entity_b",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["users.id"],
            name="fk_merge_review_reviewer",
            ondelete="SET NULL",
        ),
        # Unique constraint on pair
        sa.UniqueConstraint(
            "tenant_id",
            "entity_a_id",
            "entity_b_id",
            name="uq_merge_review_pair",
        ),
    )

    # Create standard indexes
    op.create_index(
        "idx_review_tenant",
        "merge_review_queue",
        ["tenant_id"],
    )
    op.create_index(
        "idx_review_entity_a",
        "merge_review_queue",
        ["entity_a_id"],
    )
    op.create_index(
        "idx_review_entity_b",
        "merge_review_queue",
        ["entity_b_id"],
    )
    op.create_index(
        "idx_review_status",
        "merge_review_queue",
        ["status"],
    )

    # Create partial index for pending items sorted by priority
    # This optimizes the common query pattern: "get next items to review"
    op.create_index(
        "idx_review_pending_priority",
        "merge_review_queue",
        ["tenant_id", sa.text("review_priority DESC")],
        postgresql_where=sa.text("status = 'pending'"),
    )

    # Enable Row Level Security
    op.execute("ALTER TABLE merge_review_queue ENABLE ROW LEVEL SECURITY")

    # Create RLS policy for tenant isolation
    op.execute("""
        CREATE POLICY merge_review_queue_tenant_isolation ON merge_review_queue
        FOR ALL
        USING (tenant_id = current_setting('app.current_tenant_id')::uuid)
        WITH CHECK (tenant_id = current_setting('app.current_tenant_id')::uuid)
    """)

    # Grant permissions to app user
    op.execute("""
        GRANT SELECT, INSERT, UPDATE, DELETE ON merge_review_queue
        TO knowledge_mapper_app_user
    """)


def downgrade() -> None:
    """Drop merge_review_queue table and enum."""

    # Drop RLS policy first
    op.execute(
        "DROP POLICY IF EXISTS merge_review_queue_tenant_isolation ON merge_review_queue"
    )

    # Drop the table (indexes are dropped automatically)
    op.drop_table("merge_review_queue")

    # Drop the enum type
    op.execute("DROP TYPE IF EXISTS merge_review_status")
