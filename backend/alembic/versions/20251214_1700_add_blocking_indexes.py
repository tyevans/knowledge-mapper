"""Add blocking indexes for efficient candidate identification

Revision ID: p6q7r8s9t0u1
Revises: o5p6q7r8s9t0
Create Date: 2025-12-14 17:00:00.000000

Creates specialized indexes to support efficient blocking during entity
consolidation. Blocking indexes enable rapid identification of potential
duplicate candidates without requiring full table scans.

Index Types:
1. Composite indexes on (tenant_id, entity_type, name_soundex) for phonetic blocking
2. Partial indexes for canonical entities only (aliases excluded from blocking)
3. GIN trigram indexes for fuzzy string matching
4. Composite indexes for type-based blocking within tenants

These indexes support O(log n) candidate identification rather than O(n^2)
pairwise comparison.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "p6q7r8s9t0u1"
down_revision: Union[str, None] = "o5p6q7r8s9t0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create blocking indexes for candidate identification."""

    # Enable pg_trgm extension for trigram similarity
    # This provides similarity operators: %, <->, similarity(), word_similarity()
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # Index 1: Composite index for phonetic blocking by entity type
    # Used when blocking within entity type groups (e.g., all PERSONs with same soundex)
    # Partial index only includes canonical entities
    op.create_index(
        "idx_blocking_soundex_type",
        "extracted_entities",
        ["tenant_id", "entity_type", "name_soundex"],
        postgresql_where=sa.text("is_canonical = true"),
    )

    # Index 2: Composite index for normalized name blocking
    # Enables exact match on normalized names within entity type
    op.create_index(
        "idx_blocking_normalized_type",
        "extracted_entities",
        ["tenant_id", "entity_type", "normalized_name"],
        postgresql_where=sa.text("is_canonical = true"),
    )

    # Index 3: GIN trigram index on entity name for fuzzy matching
    # Enables similarity search: WHERE name % 'search_term'
    # Only includes canonical entities with non-null names
    op.execute(
        """
        CREATE INDEX idx_blocking_name_trigram
        ON extracted_entities
        USING gin (name gin_trgm_ops)
        WHERE is_canonical = true
        """
    )

    # Index 4: GIN trigram index on normalized_name for fuzzy matching
    # Normalized names provide better matching for entity consolidation
    op.execute(
        """
        CREATE INDEX idx_blocking_normalized_trigram
        ON extracted_entities
        USING gin (normalized_name gin_trgm_ops)
        WHERE is_canonical = true
        """
    )

    # Index 5: Composite index for efficient canonical entity listing per tenant
    # Supports queries that list canonical entities by type for blocking
    op.create_index(
        "idx_canonical_entities_type",
        "extracted_entities",
        ["tenant_id", "is_canonical", "entity_type"],
        postgresql_where=sa.text("is_canonical = true"),
    )

    # Index 6: Index on source_page_id for same-page blocking
    # Entities from the same page often need to be compared
    op.create_index(
        "idx_blocking_source_page",
        "extracted_entities",
        ["tenant_id", "source_page_id"],
        postgresql_where=sa.text("is_canonical = true"),
    )

    # Index 7: Partial index for entities with embeddings (for embedding-based blocking)
    # This helps quickly identify which entities can participate in embedding similarity
    op.execute(
        """
        CREATE INDEX idx_canonical_with_embedding
        ON extracted_entities (tenant_id, entity_type)
        WHERE is_canonical = true AND embedding IS NOT NULL
        """
    )

    # Add comments for documentation
    op.execute(
        """
        COMMENT ON INDEX idx_blocking_soundex_type IS
        'Composite index for phonetic blocking by soundex within entity type'
        """
    )

    op.execute(
        """
        COMMENT ON INDEX idx_blocking_normalized_type IS
        'Composite index for exact normalized name matching within entity type'
        """
    )

    op.execute(
        """
        COMMENT ON INDEX idx_blocking_name_trigram IS
        'GIN trigram index for fuzzy name matching during blocking'
        """
    )

    op.execute(
        """
        COMMENT ON INDEX idx_blocking_normalized_trigram IS
        'GIN trigram index for fuzzy normalized name matching during blocking'
        """
    )

    op.execute(
        """
        COMMENT ON INDEX idx_canonical_entities_type IS
        'Composite index for listing canonical entities by type per tenant'
        """
    )

    op.execute(
        """
        COMMENT ON INDEX idx_blocking_source_page IS
        'Index for same-page blocking queries'
        """
    )

    op.execute(
        """
        COMMENT ON INDEX idx_canonical_with_embedding IS
        'Index for entities available for embedding similarity blocking'
        """
    )


def downgrade() -> None:
    """Remove blocking indexes."""

    # Drop indexes in reverse order
    op.drop_index("idx_canonical_with_embedding", table_name="extracted_entities")
    op.drop_index("idx_blocking_source_page", table_name="extracted_entities")
    op.drop_index("idx_canonical_entities_type", table_name="extracted_entities")
    op.drop_index("idx_blocking_normalized_trigram", table_name="extracted_entities")
    op.drop_index("idx_blocking_name_trigram", table_name="extracted_entities")
    op.drop_index("idx_blocking_normalized_type", table_name="extracted_entities")
    op.drop_index("idx_blocking_soundex_type", table_name="extracted_entities")

    # Note: We intentionally do NOT drop the pg_trgm extension here
    # as it may be used by other parts of the system.
    # If needed, drop manually: DROP EXTENSION IF EXISTS pg_trgm CASCADE;
