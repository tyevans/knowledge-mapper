"""Add soundex generated column to extracted_entities

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2025-12-14 12:00:00.000000

Enables the fuzzystrmatch extension and adds a soundex generated column
to extracted_entities for phonetic blocking during entity consolidation.

The name_soundex column is automatically computed by PostgreSQL whenever
the name column changes, enabling efficient phonetic similarity lookups.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "k1l2m3n4o5p6"
down_revision: Union[str, None] = "j0k1l2m3n4o5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Enable fuzzystrmatch extension and add soundex generated column."""

    # Enable fuzzystrmatch extension for soundex function
    # This provides phonetic encoding functions: soundex, metaphone, dmetaphone
    op.execute("CREATE EXTENSION IF NOT EXISTS fuzzystrmatch")

    # Add generated column for soundex of entity name
    # PostgreSQL 12+ supports GENERATED ALWAYS AS ... STORED
    # Soundex returns a 4-character code representing phonetic similarity
    op.execute("""
        ALTER TABLE extracted_entities
        ADD COLUMN name_soundex VARCHAR(4)
        GENERATED ALWAYS AS (soundex(name)) STORED
    """)

    # Create composite index for efficient blocking by soundex within tenant
    # Partial index only includes canonical entities (aliases don't need blocking)
    op.create_index(
        "idx_entities_soundex_tenant",
        "extracted_entities",
        ["tenant_id", "name_soundex"],
        postgresql_where=sa.text("is_canonical = true"),
    )

    # Add descriptive comment to the column
    op.execute("""
        COMMENT ON COLUMN extracted_entities.name_soundex IS
        'Soundex phonetic encoding of entity name for blocking queries'
    """)


def downgrade() -> None:
    """Remove soundex column and extension."""

    # Drop the composite index first
    op.drop_index("idx_entities_soundex_tenant", table_name="extracted_entities")

    # Drop the generated column
    op.drop_column("extracted_entities", "name_soundex")

    # Note: We intentionally do NOT drop the fuzzystrmatch extension here
    # as it may be used by other parts of the system or cause issues.
    # If needed, drop manually: DROP EXTENSION IF EXISTS fuzzystrmatch CASCADE;
