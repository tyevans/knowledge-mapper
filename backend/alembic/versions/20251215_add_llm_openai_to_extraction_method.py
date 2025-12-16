"""Add llm_openai to extraction_method enum.

Revision ID: add_llm_openai_enum
Revises: None
Create Date: 2025-12-15

This migration adds the 'llm_openai' value to the extraction_method enum type
to support OpenAI GPT-based entity extraction.
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "add_llm_openai_enum"
down_revision = None  # Will be determined by alembic
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add llm_openai to extraction_method enum."""
    # PostgreSQL allows adding values to enums with ALTER TYPE
    op.execute("ALTER TYPE extraction_method ADD VALUE IF NOT EXISTS 'llm_openai'")


def downgrade() -> None:
    """Remove llm_openai from extraction_method enum.

    Note: PostgreSQL does not support removing values from enums directly.
    A full recreation of the enum type would be needed, which requires
    dropping all dependent columns first. For safety, we leave the value in place.
    """
    # Cannot easily remove enum values in PostgreSQL
    # Would require recreating the type and all dependent columns
    pass
