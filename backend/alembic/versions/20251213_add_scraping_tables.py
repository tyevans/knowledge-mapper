"""Add scraping tables for web scraping and entity extraction

Revision ID: d4e5f6g7h8i9
Revises: c3d4e5f6g7h8
Create Date: 2025-12-13 14:00:00.000000

Creates tables for:
- scraping_jobs: Job configuration and status
- scraped_pages: Raw scraped page content
- extracted_entities: Entities extracted from pages
- entity_relationships: Relationships between entities

All tables have RLS policies for tenant isolation.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d4e5f6g7h8i9"
down_revision: Union[str, None] = "c3d4e5f6g7h8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Create scraping tables with RLS policies.
    """
    # Create enum types using raw SQL (asyncpg has issues with ENUM.create() checkfirst=True)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'job_status') THEN
                CREATE TYPE job_status AS ENUM ('pending', 'queued', 'running', 'paused', 'completed', 'failed', 'cancelled');
            END IF;
        END
        $$;
    """)

    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'entity_type') THEN
                CREATE TYPE entity_type AS ENUM ('person', 'organization', 'location', 'event', 'product', 'concept', 'document', 'date', 'custom');
            END IF;
        END
        $$;
    """)

    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'extraction_method') THEN
                CREATE TYPE extraction_method AS ENUM ('schema_org', 'open_graph', 'llm_claude', 'pattern', 'spacy', 'hybrid');
            END IF;
        END
        $$;
    """)

    # Reference the enums for use in table creation (don't create, we already did above)
    job_status_enum = postgresql.ENUM(
        'pending', 'queued', 'running', 'paused', 'completed', 'failed', 'cancelled',
        name='job_status',
        create_type=False
    )

    entity_type_enum = postgresql.ENUM(
        'person', 'organization', 'location', 'event', 'product', 'concept', 'document', 'date', 'custom',
        name='entity_type',
        create_type=False
    )

    extraction_method_enum = postgresql.ENUM(
        'schema_org', 'open_graph', 'llm_claude', 'pattern', 'spacy', 'hybrid',
        name='extraction_method',
        create_type=False
    )

    # =========================================================================
    # Create scraping_jobs table
    # =========================================================================
    op.create_table(
        'scraping_jobs',
        sa.Column('id', sa.UUID(), nullable=False, comment='UUID primary key'),
        sa.Column('tenant_id', sa.UUID(), nullable=False, comment='Tenant (RLS enforced)'),
        sa.Column('created_by_user_id', sa.String(255), nullable=False, comment='User who created the job'),
        sa.Column('name', sa.String(255), nullable=False, comment='Job name'),
        sa.Column('start_url', sa.String(2048), nullable=False, comment='Starting URL'),
        sa.Column('allowed_domains', postgresql.JSONB(), nullable=False, server_default='[]', comment='Allowed domains'),
        sa.Column('url_patterns', postgresql.JSONB(), nullable=True, comment='URL include patterns'),
        sa.Column('excluded_patterns', postgresql.JSONB(), nullable=True, comment='URL exclude patterns'),
        sa.Column('crawl_depth', sa.Integer(), nullable=False, server_default='2', comment='Max crawl depth'),
        sa.Column('max_pages', sa.Integer(), nullable=False, server_default='100', comment='Max pages to scrape'),
        sa.Column('crawl_speed', sa.Float(), nullable=False, server_default='1.0', comment='Requests per second'),
        sa.Column('respect_robots_txt', sa.Boolean(), nullable=False, server_default='true', comment='Honor robots.txt'),
        sa.Column('use_llm_extraction', sa.Boolean(), nullable=False, server_default='true', comment='Use LLM extraction'),
        sa.Column('custom_settings', postgresql.JSONB(), nullable=False, server_default='{}', comment='Custom Scrapy settings'),
        sa.Column('status', job_status_enum, nullable=False, server_default='pending', comment='Job status'),
        sa.Column('celery_task_id', sa.String(255), nullable=True, comment='Celery task ID'),
        sa.Column('pages_crawled', sa.Integer(), nullable=False, server_default='0', comment='Pages scraped'),
        sa.Column('entities_extracted', sa.Integer(), nullable=False, server_default='0', comment='Entities extracted'),
        sa.Column('errors_count', sa.Integer(), nullable=False, server_default='0', comment='Error count'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True, comment='Start time'),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True, comment='Completion time'),
        sa.Column('error_message', sa.Text(), nullable=True, comment='Error message'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE')
    )

    op.create_index('ix_scraping_jobs_id', 'scraping_jobs', ['id'])
    op.create_index('ix_scraping_jobs_tenant_id', 'scraping_jobs', ['tenant_id'])
    op.create_index('ix_scraping_jobs_status', 'scraping_jobs', ['status'])
    op.create_index('ix_scraping_jobs_created_by', 'scraping_jobs', ['created_by_user_id'])

    # =========================================================================
    # Create scraped_pages table
    # =========================================================================
    op.create_table(
        'scraped_pages',
        sa.Column('id', sa.UUID(), nullable=False, comment='UUID primary key'),
        sa.Column('tenant_id', sa.UUID(), nullable=False, comment='Tenant (RLS enforced)'),
        sa.Column('job_id', sa.UUID(), nullable=False, comment='Parent job'),
        sa.Column('url', sa.String(2048), nullable=False, comment='Page URL'),
        sa.Column('canonical_url', sa.String(2048), nullable=True, comment='Canonical URL'),
        sa.Column('content_hash', sa.String(64), nullable=False, comment='SHA-256 hash'),
        sa.Column('html_content', sa.Text(), nullable=False, comment='Raw HTML'),
        sa.Column('text_content', sa.Text(), nullable=False, comment='Extracted text'),
        sa.Column('title', sa.String(512), nullable=True, comment='Page title'),
        sa.Column('meta_description', sa.Text(), nullable=True, comment='Meta description'),
        sa.Column('meta_keywords', sa.Text(), nullable=True, comment='Meta keywords'),
        sa.Column('schema_org_data', postgresql.JSONB(), nullable=False, server_default='[]', comment='Schema.org data'),
        sa.Column('open_graph_data', postgresql.JSONB(), nullable=False, server_default='{}', comment='Open Graph data'),
        sa.Column('http_status', sa.Integer(), nullable=False, comment='HTTP status code'),
        sa.Column('content_type', sa.String(255), nullable=False, server_default='text/html', comment='Content-Type'),
        sa.Column('response_headers', postgresql.JSONB(), nullable=False, server_default='{}', comment='Response headers'),
        sa.Column('crawled_at', sa.DateTime(timezone=True), nullable=False, comment='Crawl timestamp'),
        sa.Column('depth', sa.Integer(), nullable=False, server_default='0', comment='Link depth'),
        sa.Column('extraction_status', sa.String(50), nullable=False, server_default='pending', comment='Extraction status'),
        sa.Column('extracted_at', sa.DateTime(timezone=True), nullable=True, comment='Extraction timestamp'),
        sa.Column('extraction_error', sa.Text(), nullable=True, comment='Extraction error'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['job_id'], ['scraping_jobs.id'], ondelete='CASCADE')
    )

    op.create_index('ix_scraped_pages_id', 'scraped_pages', ['id'])
    op.create_index('ix_scraped_pages_tenant_id', 'scraped_pages', ['tenant_id'])
    op.create_index('ix_scraped_pages_job_id', 'scraped_pages', ['job_id'])
    op.create_index('ix_scraped_pages_url', 'scraped_pages', ['url'])
    op.create_index('ix_scraped_pages_content_hash', 'scraped_pages', ['content_hash'])
    op.create_index('ix_scraped_pages_extraction_status', 'scraped_pages', ['extraction_status'])

    # =========================================================================
    # Create extracted_entities table
    # =========================================================================
    op.create_table(
        'extracted_entities',
        sa.Column('id', sa.UUID(), nullable=False, comment='UUID primary key'),
        sa.Column('tenant_id', sa.UUID(), nullable=False, comment='Tenant (RLS enforced)'),
        sa.Column('source_page_id', sa.UUID(), nullable=False, comment='Source page'),
        sa.Column('entity_type', entity_type_enum, nullable=False, comment='Entity type'),
        sa.Column('name', sa.String(512), nullable=False, comment='Entity name'),
        sa.Column('normalized_name', sa.String(512), nullable=False, comment='Normalized name'),
        sa.Column('description', sa.Text(), nullable=True, comment='Entity description'),
        sa.Column('external_ids', postgresql.JSONB(), nullable=False, server_default='{}', comment='External IDs'),
        sa.Column('properties', postgresql.JSONB(), nullable=False, server_default='{}', comment='Entity properties'),
        sa.Column('extraction_method', extraction_method_enum, nullable=False, comment='Extraction method'),
        sa.Column('confidence_score', sa.Float(), nullable=False, server_default='1.0', comment='Confidence score'),
        sa.Column('source_text', sa.Text(), nullable=True, comment='Source text snippet'),
        sa.Column('neo4j_node_id', sa.String(255), nullable=True, comment='Neo4j node ID'),
        sa.Column('synced_to_neo4j', sa.Boolean(), nullable=False, server_default='false', comment='Neo4j sync status'),
        sa.Column('synced_at', sa.DateTime(timezone=True), nullable=True, comment='Neo4j sync timestamp'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_page_id'], ['scraped_pages.id'], ondelete='CASCADE')
    )

    op.create_index('ix_extracted_entities_id', 'extracted_entities', ['id'])
    op.create_index('ix_extracted_entities_tenant_id', 'extracted_entities', ['tenant_id'])
    op.create_index('ix_extracted_entities_source_page_id', 'extracted_entities', ['source_page_id'])
    op.create_index('ix_extracted_entities_entity_type', 'extracted_entities', ['entity_type'])
    op.create_index('ix_extracted_entities_name', 'extracted_entities', ['name'])
    op.create_index('ix_extracted_entities_normalized_name', 'extracted_entities', ['normalized_name'])
    op.create_index('ix_extracted_entities_extraction_method', 'extracted_entities', ['extraction_method'])
    op.create_index('ix_extracted_entities_synced_to_neo4j', 'extracted_entities', ['synced_to_neo4j'])

    # =========================================================================
    # Create entity_relationships table
    # =========================================================================
    op.create_table(
        'entity_relationships',
        sa.Column('id', sa.UUID(), nullable=False, comment='UUID primary key'),
        sa.Column('tenant_id', sa.UUID(), nullable=False, comment='Tenant (RLS enforced)'),
        sa.Column('source_entity_id', sa.UUID(), nullable=False, comment='Source entity'),
        sa.Column('target_entity_id', sa.UUID(), nullable=False, comment='Target entity'),
        sa.Column('relationship_type', sa.String(100), nullable=False, comment='Relationship type'),
        sa.Column('properties', postgresql.JSONB(), nullable=False, server_default='{}', comment='Relationship properties'),
        sa.Column('confidence_score', sa.Float(), nullable=False, server_default='1.0', comment='Confidence score'),
        sa.Column('neo4j_relationship_id', sa.String(255), nullable=True, comment='Neo4j relationship ID'),
        sa.Column('synced_to_neo4j', sa.Boolean(), nullable=False, server_default='false', comment='Neo4j sync status'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_entity_id'], ['extracted_entities.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['target_entity_id'], ['extracted_entities.id'], ondelete='CASCADE')
    )

    op.create_index('ix_entity_relationships_id', 'entity_relationships', ['id'])
    op.create_index('ix_entity_relationships_tenant_id', 'entity_relationships', ['tenant_id'])
    op.create_index('ix_entity_relationships_source_entity_id', 'entity_relationships', ['source_entity_id'])
    op.create_index('ix_entity_relationships_target_entity_id', 'entity_relationships', ['target_entity_id'])
    op.create_index('ix_entity_relationships_relationship_type', 'entity_relationships', ['relationship_type'])
    op.create_index('ix_entity_relationships_synced_to_neo4j', 'entity_relationships', ['synced_to_neo4j'])

    # =========================================================================
    # Enable Row-Level Security (RLS) on all tables
    # =========================================================================
    for table in ['scraping_jobs', 'scraped_pages', 'extracted_entities', 'entity_relationships']:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")

        # Create RLS policy with USING (SELECT/UPDATE/DELETE) and WITH CHECK (INSERT/UPDATE)
        op.execute(f"""
            CREATE POLICY tenant_isolation_policy ON {table}
            USING (tenant_id = COALESCE(
                NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID,
                '00000000-0000-0000-0000-000000000000'::UUID
            ))
            WITH CHECK (tenant_id = COALESCE(
                NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID,
                '00000000-0000-0000-0000-000000000000'::UUID
            ))
        """)


def downgrade() -> None:
    """
    Drop scraping tables and enum types.
    """
    # Drop RLS policies and tables
    for table in ['entity_relationships', 'extracted_entities', 'scraped_pages', 'scraping_jobs']:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.drop_table(table)

    # Drop enum types using raw SQL (asyncpg compatibility)
    op.execute("DROP TYPE IF EXISTS extraction_method")
    op.execute("DROP TYPE IF EXISTS entity_type")
    op.execute("DROP TYPE IF EXISTS job_status")
