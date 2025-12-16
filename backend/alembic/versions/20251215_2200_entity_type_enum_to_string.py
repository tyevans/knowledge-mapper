"""Convert entity_type from PostgreSQL Enum to String.

Revision ID: u1v2w3x4y5z6
Revises: t0u1v2w3x4y5
Create Date: 2025-12-15

This migration converts the entity_type column from a PostgreSQL Enum
to a String(100) to support dynamic domain-specific entity types.

This is a CRITICAL migration for the Adaptive Extraction Strategy feature.
It enables storing arbitrary entity types like 'character', 'theme', 'plot_point'
that aren't predefined in the EntityType enum.

Migration Steps:
1. Add new string column entity_type_new
2. Copy data from enum column to string column
3. Make new column NOT NULL
4. Drop the old enum column
5. Rename new column to entity_type
6. Add index on the new string column
7. Drop the PostgreSQL enum type
8. Add original_entity_type column for LLM type tracking
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "u1v2w3x4y5z6"
down_revision: Union[str, None] = "t0u1v2w3x4y5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Convert entity_type from Enum to String."""

    # Step 1: Add new string column (temporarily nullable)
    op.add_column(
        "extracted_entities",
        sa.Column(
            "entity_type_new",
            sa.String(100),
            nullable=True,
            comment="Entity type as string (migration intermediate)",
        ),
    )

    # Step 2: Copy data from enum to string (cast enum to text)
    # PostgreSQL enum values can be cast to text directly
    op.execute("""
        UPDATE extracted_entities
        SET entity_type_new = entity_type::text
    """)

    # Step 3: Make new column NOT NULL after data migration
    op.alter_column(
        "extracted_entities",
        "entity_type_new",
        nullable=False,
    )

    # Step 4: Drop the old enum column and its index
    # First drop the index if it exists
    op.execute("""
        DROP INDEX IF EXISTS ix_extracted_entities_entity_type
    """)
    op.drop_column("extracted_entities", "entity_type")

    # Step 5: Rename new column to entity_type
    op.alter_column(
        "extracted_entities",
        "entity_type_new",
        new_column_name="entity_type",
        comment="Entity type (string, supports legacy enum values and domain-specific types)",
    )

    # Step 6: Add index on the new string column
    op.create_index(
        "ix_extracted_entities_entity_type",
        "extracted_entities",
        ["entity_type"],
    )

    # Step 7: Drop the PostgreSQL enum type (no longer needed)
    # Note: Using CASCADE to handle any remaining dependencies
    op.execute("DROP TYPE IF EXISTS entity_type CASCADE")

    # Step 8: Add original_entity_type column for tracking LLM-provided types
    op.add_column(
        "extracted_entities",
        sa.Column(
            "original_entity_type",
            sa.String(100),
            nullable=True,
            comment="Original entity type from LLM before normalization (if different)",
        ),
    )


def downgrade() -> None:
    """Revert entity_type back to Enum.

    WARNING: This downgrade may fail if entities have types not in the enum.
    Domain-specific types like 'character', 'theme', 'plot_point' will cause
    the cast to fail. In production, a data cleanup step would be needed first.
    """

    # Step 1: Drop original_entity_type column
    op.drop_column("extracted_entities", "original_entity_type")

    # Step 2: Recreate the enum type with all original values
    entity_type_enum = sa.Enum(
        'person', 'organization', 'location', 'event', 'product',
        'concept', 'document', 'date', 'custom',
        'function', 'class', 'module', 'pattern', 'example',
        'parameter', 'return_type', 'exception',
        name='entity_type'
    )
    entity_type_enum.create(op.get_bind(), checkfirst=True)

    # Step 3: Add new enum column (temporarily nullable)
    op.add_column(
        "extracted_entities",
        sa.Column(
            "entity_type_enum",
            entity_type_enum,
            nullable=True,
        ),
    )

    # Step 4: Copy data from string to enum
    # First, map any unknown types to 'custom'
    op.execute("""
        UPDATE extracted_entities
        SET entity_type = 'custom'
        WHERE entity_type NOT IN (
            'person', 'organization', 'location', 'event', 'product',
            'concept', 'document', 'date', 'custom',
            'function', 'class', 'module', 'pattern', 'example',
            'parameter', 'return_type', 'exception'
        )
    """)

    # Now cast to enum
    op.execute("""
        UPDATE extracted_entities
        SET entity_type_enum = entity_type::entity_type
    """)

    # Step 5: Make NOT NULL
    op.alter_column(
        "extracted_entities",
        "entity_type_enum",
        nullable=False,
    )

    # Step 6: Drop string column and its index
    op.drop_index("ix_extracted_entities_entity_type", table_name="extracted_entities")
    op.drop_column("extracted_entities", "entity_type")

    # Step 7: Rename enum column
    op.alter_column(
        "extracted_entities",
        "entity_type_enum",
        new_column_name="entity_type",
    )

    # Step 8: Recreate enum index
    op.create_index(
        "ix_extracted_entities_entity_type",
        "extracted_entities",
        ["entity_type"],
    )
