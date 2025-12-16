"""Create entity_aliases table

Revision ID: l2m3n4o5p6q7
Revises: k1l2m3n4o5p6
Create Date: 2025-12-14 13:00:00.000000

Creates the entity_aliases table to track original entity names that were
merged into canonical entities. This supports:
- Querying by any historical name
- Displaying alias information in UI
- Enabling undo operations with full provenance
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "l2m3n4o5p6q7"
down_revision: Union[str, None] = "k1l2m3n4o5p6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create entity_aliases table with RLS and indexes."""

    # Create entity_aliases table
    op.create_table(
        "entity_aliases",
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
            comment="Tenant this alias belongs to (RLS enforced)",
        ),
        # Canonical entity reference
        sa.Column(
            "canonical_entity_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="The canonical entity this is an alias of",
        ),
        # Alias information
        sa.Column(
            "alias_name",
            sa.String(512),
            nullable=False,
            comment="Original name of the merged entity",
        ),
        sa.Column(
            "alias_normalized_name",
            sa.String(512),
            nullable=False,
            comment="Normalized version of alias name for searching",
        ),
        # Provenance tracking
        sa.Column(
            "original_entity_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Original entity ID before merge (for undo)",
        ),
        sa.Column(
            "source_page_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Page the original entity was extracted from",
        ),
        sa.Column(
            "merge_event_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Reference to the merge event for provenance",
        ),
        sa.Column(
            "merged_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="When the entity was merged",
        ),
        sa.Column(
            "merge_reason",
            sa.String(100),
            nullable=True,
            comment="Reason for merge (auto_high_confidence, user_approved, batch)",
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
            name="fk_entity_aliases_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["canonical_entity_id"],
            ["extracted_entities.id"],
            name="fk_entity_aliases_canonical_entity",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_page_id"],
            ["scraped_pages.id"],
            name="fk_entity_aliases_source_page",
            ondelete="SET NULL",
        ),
    )

    # Create indexes for efficient queries
    op.create_index(
        "idx_aliases_tenant",
        "entity_aliases",
        ["tenant_id"],
    )
    op.create_index(
        "idx_aliases_canonical",
        "entity_aliases",
        ["canonical_entity_id"],
    )
    op.create_index(
        "idx_aliases_name",
        "entity_aliases",
        ["tenant_id", "alias_normalized_name"],
    )
    op.create_index(
        "idx_aliases_original",
        "entity_aliases",
        ["original_entity_id"],
    )

    # Enable Row Level Security
    op.execute("ALTER TABLE entity_aliases ENABLE ROW LEVEL SECURITY")

    # Create RLS policy for tenant isolation
    op.execute("""
        CREATE POLICY entity_aliases_tenant_isolation ON entity_aliases
        FOR ALL
        USING (tenant_id = current_setting('app.current_tenant_id')::uuid)
        WITH CHECK (tenant_id = current_setting('app.current_tenant_id')::uuid)
    """)

    # Grant permissions to app user
    op.execute("""
        GRANT SELECT, INSERT, UPDATE, DELETE ON entity_aliases
        TO knowledge_mapper_app_user
    """)


def downgrade() -> None:
    """Drop entity_aliases table."""

    # Drop RLS policy first
    op.execute(
        "DROP POLICY IF EXISTS entity_aliases_tenant_isolation ON entity_aliases"
    )

    # Drop the table (indexes are dropped automatically)
    op.drop_table("entity_aliases")
