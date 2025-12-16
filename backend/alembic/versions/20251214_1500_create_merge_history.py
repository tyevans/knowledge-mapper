"""Create merge_history table

Revision ID: n4o5p6q7r8s9
Revises: m3n4o5p6q7r8
Create Date: 2025-12-14 15:00:00.000000

Creates the merge_history table for tracking entity consolidation operations.
This is a denormalized projection of merge events for efficient querying,
supporting the audit trail and undo functionality.

Includes a GIN index on the UUID array for efficient "find by affected entity" queries.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "n4o5p6q7r8s9"
down_revision: Union[str, None] = "m3n4o5p6q7r8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create merge_history table with RLS and indexes."""

    # Create enum type for merge event type (use raw SQL with IF NOT EXISTS)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'merge_event_type') THEN
                CREATE TYPE merge_event_type AS ENUM ('entities_merged', 'merge_undone', 'entity_split');
            END IF;
        END$$;
    """)

    # Create merge_history table
    op.create_table(
        "merge_history",
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
            comment="Tenant this history belongs to (RLS enforced)",
        ),
        # Event reference
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            unique=True,
            comment="Reference to the source domain event",
        ),
        sa.Column(
            "event_type",
            postgresql.ENUM(
                "entities_merged",
                "merge_undone",
                "entity_split",
                name="merge_event_type",
                create_type=False,  # Already created above
            ),
            nullable=False,
            comment="Type of merge operation",
        ),
        # Entity references
        sa.Column(
            "canonical_entity_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="The canonical entity (for merges)",
        ),
        sa.Column(
            "affected_entity_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            comment="All entity IDs involved in the operation",
        ),
        # Operation details
        sa.Column(
            "merge_reason",
            sa.String(100),
            nullable=True,
            comment="Why the merge occurred (auto_high_confidence, user_approved, batch)",
        ),
        sa.Column(
            "similarity_scores",
            postgresql.JSONB(),
            nullable=True,
            comment="Similarity scores at time of merge",
        ),
        sa.Column(
            "details",
            postgresql.JSONB(),
            nullable=True,
            comment="Additional operation details",
        ),
        # Who and when
        sa.Column(
            "performed_by",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="User who performed/approved the operation",
        ),
        sa.Column(
            "performed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="When the operation occurred",
        ),
        # Undo tracking
        sa.Column(
            "undone",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="Whether this merge has been undone",
        ),
        sa.Column(
            "undone_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the merge was undone",
        ),
        sa.Column(
            "undone_by",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Who undone the merge",
        ),
        sa.Column(
            "undo_reason",
            sa.Text(),
            nullable=True,
            comment="Reason for undoing the merge",
        ),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="Record creation timestamp",
        ),
        # Foreign keys
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_merge_history_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["canonical_entity_id"],
            ["extracted_entities.id"],
            name="fk_merge_history_canonical_entity",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["performed_by"],
            ["users.id"],
            name="fk_merge_history_performer",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["undone_by"],
            ["users.id"],
            name="fk_merge_history_undoer",
            ondelete="SET NULL",
        ),
    )

    # Create standard indexes
    op.create_index(
        "idx_history_tenant",
        "merge_history",
        ["tenant_id"],
    )
    op.create_index(
        "idx_history_event_type",
        "merge_history",
        ["event_type"],
    )
    op.create_index(
        "idx_history_canonical",
        "merge_history",
        ["canonical_entity_id"],
    )

    # Time-based index for "recent history" queries
    op.create_index(
        "idx_history_time",
        "merge_history",
        ["tenant_id", sa.text("performed_at DESC")],
    )

    # GIN index for efficient array queries (find history by affected entity)
    # This allows queries like: WHERE :entity_id = ANY(affected_entity_ids)
    op.create_index(
        "idx_history_affected_entities",
        "merge_history",
        ["affected_entity_ids"],
        postgresql_using="gin",
    )

    # Enable Row Level Security
    op.execute("ALTER TABLE merge_history ENABLE ROW LEVEL SECURITY")

    # Create RLS policy for tenant isolation
    op.execute("""
        CREATE POLICY merge_history_tenant_isolation ON merge_history
        FOR ALL
        USING (tenant_id = current_setting('app.current_tenant_id')::uuid)
        WITH CHECK (tenant_id = current_setting('app.current_tenant_id')::uuid)
    """)

    # Grant permissions to app user (no DELETE - history is immutable)
    op.execute("""
        GRANT SELECT, INSERT, UPDATE ON merge_history
        TO knowledge_mapper_app_user
    """)


def downgrade() -> None:
    """Drop merge_history table and enum."""

    # Drop RLS policy first
    op.execute(
        "DROP POLICY IF EXISTS merge_history_tenant_isolation ON merge_history"
    )

    # Drop the table (indexes are dropped automatically)
    op.drop_table("merge_history")

    # Drop the enum type
    op.execute("DROP TYPE IF EXISTS merge_event_type")
