"""Add canonical and alias columns to extracted_entities

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2025-12-14 10:00:00.000000

Adds columns for entity consolidation:
- is_alias_of: Self-referential FK to canonical entity
- is_canonical: Boolean flag for canonical entities

These columns support the entity merge/consolidation feature where
similar entities can be linked to a canonical representation.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "i9j0k1l2m3n4"
down_revision: Union[str, None] = "h8i9j0k1l2m3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add canonical/alias tracking columns to extracted_entities."""

    # Add is_alias_of column (self-referential FK)
    op.add_column(
        "extracted_entities",
        sa.Column(
            "is_alias_of",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="If set, this entity is an alias of the canonical entity with this ID",
        ),
    )

    # Add foreign key constraint for is_alias_of
    op.create_foreign_key(
        "fk_extracted_entities_is_alias_of",
        "extracted_entities",
        "extracted_entities",
        ["is_alias_of"],
        ["id"],
        ondelete="SET NULL",
    )

    # Add is_canonical column with server default
    op.add_column(
        "extracted_entities",
        sa.Column(
            "is_canonical",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="Whether this is a canonical entity (not an alias)",
        ),
    )

    # Create partial index for alias lookups (only non-null values)
    op.create_index(
        "idx_entities_alias_of",
        "extracted_entities",
        ["is_alias_of"],
        postgresql_where=sa.text("is_alias_of IS NOT NULL"),
    )

    # Create partial index for canonical entity lookups within a tenant
    op.create_index(
        "idx_entities_is_canonical",
        "extracted_entities",
        ["tenant_id", "is_canonical"],
        postgresql_where=sa.text("is_canonical = true"),
    )


def downgrade() -> None:
    """Remove canonical/alias tracking columns."""

    # Drop indexes first
    op.drop_index("idx_entities_is_canonical", table_name="extracted_entities")
    op.drop_index("idx_entities_alias_of", table_name="extracted_entities")

    # Drop foreign key
    op.drop_constraint(
        "fk_extracted_entities_is_alias_of",
        "extracted_entities",
        type_="foreignkey",
    )

    # Drop columns
    op.drop_column("extracted_entities", "is_canonical")
    op.drop_column("extracted_entities", "is_alias_of")
