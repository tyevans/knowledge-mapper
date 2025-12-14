"""Add documentation-specific entity types and Ollama extraction method

Revision ID: f6g7h8i9j0k1
Revises: e5f6g7h8i9j0
Create Date: 2025-12-13 23:00:00.000000

This migration adds:
1. New entity types for technical documentation:
   - FUNCTION: Callable functions with signatures
   - CLASS: OOP classes with methods/attributes
   - MODULE: Python modules and packages
   - PATTERN: Design patterns, architectural patterns
   - EXAMPLE: Code examples and usage demonstrations
   - PARAMETER: Function/method parameters
   - RETURN_TYPE: Function return types
   - EXCEPTION: Exception classes

2. New extraction method:
   - LLM_OLLAMA: For local Ollama LLM extraction
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6g7h8i9j0k1"
down_revision: Union[str, None] = "e5f6g7h8i9j0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add new entity types and extraction method to PostgreSQL enums."""

    # Add documentation-specific entity types
    # Note: IF NOT EXISTS requires PostgreSQL 9.3+
    op.execute("ALTER TYPE entity_type ADD VALUE IF NOT EXISTS 'function';")
    op.execute("ALTER TYPE entity_type ADD VALUE IF NOT EXISTS 'class';")
    op.execute("ALTER TYPE entity_type ADD VALUE IF NOT EXISTS 'module';")
    op.execute("ALTER TYPE entity_type ADD VALUE IF NOT EXISTS 'pattern';")
    op.execute("ALTER TYPE entity_type ADD VALUE IF NOT EXISTS 'example';")
    op.execute("ALTER TYPE entity_type ADD VALUE IF NOT EXISTS 'parameter';")
    op.execute("ALTER TYPE entity_type ADD VALUE IF NOT EXISTS 'return_type';")
    op.execute("ALTER TYPE entity_type ADD VALUE IF NOT EXISTS 'exception';")

    # Add Ollama extraction method
    op.execute("ALTER TYPE extraction_method ADD VALUE IF NOT EXISTS 'llm_ollama';")


def downgrade() -> None:
    """Cannot remove enum values in PostgreSQL - document only.

    PostgreSQL does not support removing values from enums.
    To fully downgrade, you would need to:
    1. Create new enum without these values
    2. Update all references to use new enum
    3. Drop old enum
    4. Rename new enum to old name

    Since we have no data with these types yet, this is a one-way migration.
    """
    pass
