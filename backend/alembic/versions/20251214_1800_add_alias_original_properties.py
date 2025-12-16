"""Add original entity properties to entity_aliases for undo support

Revision ID: q7r8s9t0u1v2
Revises: p6q7r8s9t0u1
Create Date: 2025-12-14 18:00:00.000000

Adds columns to entity_aliases table to store the original entity properties
that existed before a merge. This enables full restoration during undo operations.

Columns added:
- original_entity_type: The original entity type enum value
- original_normalized_name: The original normalized name
- original_description: The original description text
- original_properties: The original properties JSONB
- original_external_ids: The original external_ids JSONB
- original_confidence_score: The original confidence score
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "q7r8s9t0u1v2"
down_revision: Union[str, None] = "p6q7r8s9t0u1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add original entity property columns to entity_aliases."""

    # Add original_entity_type column (required for restoration)
    op.add_column(
        "entity_aliases",
        sa.Column(
            "original_entity_type",
            sa.String(50),
            nullable=True,  # Nullable for backwards compatibility
            comment="Original entity type before merge",
        ),
    )

    # Add original_normalized_name column
    op.add_column(
        "entity_aliases",
        sa.Column(
            "original_normalized_name",
            sa.String(512),
            nullable=True,  # Nullable for backwards compatibility
            comment="Original normalized name before merge",
        ),
    )

    # Add original_description column
    op.add_column(
        "entity_aliases",
        sa.Column(
            "original_description",
            sa.Text(),
            nullable=True,
            comment="Original description before merge",
        ),
    )

    # Add original_properties column (JSONB for flexibility)
    op.add_column(
        "entity_aliases",
        sa.Column(
            "original_properties",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default="{}",
            comment="Original entity properties JSONB before merge",
        ),
    )

    # Add original_external_ids column (JSONB)
    op.add_column(
        "entity_aliases",
        sa.Column(
            "original_external_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default="{}",
            comment="Original external identifiers JSONB before merge",
        ),
    )

    # Add original_confidence_score column
    op.add_column(
        "entity_aliases",
        sa.Column(
            "original_confidence_score",
            sa.Float(),
            nullable=True,
            server_default="1.0",
            comment="Original confidence score before merge",
        ),
    )

    # Add original_source_text column for context
    op.add_column(
        "entity_aliases",
        sa.Column(
            "original_source_text",
            sa.Text(),
            nullable=True,
            comment="Original source text snippet before merge",
        ),
    )


def downgrade() -> None:
    """Remove original entity property columns from entity_aliases."""

    op.drop_column("entity_aliases", "original_source_text")
    op.drop_column("entity_aliases", "original_confidence_score")
    op.drop_column("entity_aliases", "original_external_ids")
    op.drop_column("entity_aliases", "original_properties")
    op.drop_column("entity_aliases", "original_description")
    op.drop_column("entity_aliases", "original_normalized_name")
    op.drop_column("entity_aliases", "original_entity_type")
