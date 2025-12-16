"""Add pgvector extension and embedding column

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2025-12-14 11:00:00.000000

Enables pgvector extension and adds embedding column to extracted_entities
for semantic similarity search during entity consolidation.

Uses bge-m3 embedding model with 1024 dimensions.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "j0k1l2m3n4o5"
down_revision: Union[str, None] = "i9j0k1l2m3n4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# bge-m3 produces 1024-dimensional vectors
EMBEDDING_DIMENSION = 1024


def upgrade() -> None:
    """Create pgvector extension and add embedding column."""

    # Ensure pgvector extension is installed
    # This requires the pgvector PostgreSQL extension to be available in the database
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Import Vector type after extension is created
    from pgvector.sqlalchemy import Vector

    # Add embedding column to extracted_entities
    op.add_column(
        "extracted_entities",
        sa.Column(
            "embedding",
            Vector(EMBEDDING_DIMENSION),
            nullable=True,
            comment="bge-m3 embedding vector for semantic similarity (1024 dimensions)",
        ),
    )

    # Create HNSW index for fast similarity search
    # HNSW provides better recall than IVFFlat with acceptable build time
    # Parameters:
    #   m=16: Number of connections per element (higher = better recall, more memory)
    #   ef_construction=64: Search depth during build (higher = better index quality)
    op.execute(
        """
        CREATE INDEX ix_extracted_entities_embedding_hnsw
        ON extracted_entities
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )

    # Create partial index for tenant-scoped embedding queries
    # Only includes rows that have embeddings (non-null)
    op.execute(
        """
        CREATE INDEX ix_extracted_entities_tenant_embedding
        ON extracted_entities (tenant_id)
        WHERE embedding IS NOT NULL
        """
    )


def downgrade() -> None:
    """Remove embedding column and pgvector extension."""

    # Drop indexes first
    op.drop_index("ix_extracted_entities_tenant_embedding", table_name="extracted_entities")
    op.drop_index("ix_extracted_entities_embedding_hnsw", table_name="extracted_entities")

    # Drop column
    op.drop_column("extracted_entities", "embedding")

    # Note: We intentionally do NOT drop the vector extension here
    # as it may be used by other tables or cause issues with database state.
    # If needed, drop manually: DROP EXTENSION IF EXISTS vector CASCADE;
