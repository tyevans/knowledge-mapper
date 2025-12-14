"""Add event sourcing tables

Revision ID: a1b2c3d4e5f6
Revises: 5ba5077f1546
Create Date: 2025-12-12 23:00:00.000000

Creates tables for eventsource-py library:
- events: Main event store with optimistic locking
- event_outbox: Transactional outbox for reliable publishing
- projection_checkpoints: Projection position tracking
- dead_letter_queue: Failed event processing storage
- snapshots: Aggregate state snapshots for performance

Note: These are infrastructure tables and do NOT have RLS enabled.
They are accessed by the application using aggregate_id/tenant_id filtering.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "5ba5077f1546"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Create event sourcing infrastructure tables.
    Schema matches eventsource-py library PostgreSQLEventStore expectations.
    """
    # ==========================================================================
    # Events Table - Main event store
    # ==========================================================================
    op.create_table(
        "events",
        sa.Column(
            "global_position",
            sa.BigInteger(),
            sa.Identity(always=True),
            primary_key=True,
            comment="Global position for ordered replay across all streams",
        ),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            unique=True,
            comment="Unique event identifier",
        ),
        sa.Column(
            "aggregate_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="ID of the aggregate this event belongs to",
        ),
        sa.Column(
            "aggregate_type",
            sa.String(length=255),
            nullable=False,
            comment="Type name of the aggregate (e.g., 'Order')",
        ),
        sa.Column(
            "event_type",
            sa.String(length=255),
            nullable=False,
            comment="Type name of the event (e.g., 'OrderCreated')",
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Tenant this event belongs to (for filtering)",
        ),
        sa.Column(
            "actor_id",
            sa.String(length=255),
            nullable=True,
            comment="ID of the user/system that caused this event",
        ),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            comment="Aggregate version (optimistic concurrency)",
        ),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="When the event occurred",
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(),
            nullable=False,
            comment="Event payload as JSON",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
            comment="When the event was stored",
        ),
        sa.UniqueConstraint(
            "aggregate_id",
            "aggregate_type",
            "version",
            name="uq_events_aggregate_version",
        ),
    )

    # Events indexes
    op.create_index("idx_events_aggregate_id", "events", ["aggregate_id"])
    op.create_index("idx_events_aggregate_type", "events", ["aggregate_type"])
    op.create_index("idx_events_event_type", "events", ["event_type"])
    op.create_index("idx_events_timestamp", "events", ["timestamp"])
    op.create_index(
        "idx_events_tenant_id",
        "events",
        ["tenant_id"],
        postgresql_where=sa.text("tenant_id IS NOT NULL"),
    )
    op.create_index(
        "idx_events_type_tenant_timestamp",
        "events",
        ["aggregate_type", "tenant_id", "timestamp"],
    )
    op.create_index(
        "idx_events_aggregate_version",
        "events",
        ["aggregate_id", "aggregate_type", "version"],
    )

    # ==========================================================================
    # Event Outbox Table - Transactional outbox for reliable publishing
    # ==========================================================================
    op.create_table(
        "event_outbox",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(255), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aggregate_type", sa.String(255), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_data", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'published', 'failed')", name="chk_outbox_status"
        ),
    )

    op.create_index(
        "idx_outbox_status_created",
        "event_outbox",
        ["status", "created_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "idx_outbox_pending",
        "event_outbox",
        ["created_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index("idx_outbox_event_id", "event_outbox", ["event_id"])
    op.create_index(
        "idx_outbox_tenant_id",
        "event_outbox",
        ["tenant_id"],
        postgresql_where=sa.text("tenant_id IS NOT NULL"),
    )

    # ==========================================================================
    # Projection Checkpoints Table - Projection position tracking
    # ==========================================================================
    op.create_table(
        "projection_checkpoints",
        sa.Column("projection_name", sa.String(255), primary_key=True),
        sa.Column("last_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_event_type", sa.String(255), nullable=True),
        sa.Column("last_processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("global_position", sa.BigInteger(), nullable=True),
        sa.Column("events_processed", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    op.create_index(
        "idx_checkpoints_last_processed",
        "projection_checkpoints",
        ["last_processed_at"],
    )
    op.create_index(
        "idx_checkpoints_updated_at", "projection_checkpoints", ["updated_at"]
    )
    op.create_index(
        "idx_checkpoints_global_position",
        "projection_checkpoints",
        ["global_position"],
        postgresql_where=sa.text("global_position IS NOT NULL"),
    )

    # Auto-update trigger for updated_at
    op.execute("""
        CREATE OR REPLACE FUNCTION update_checkpoint_timestamp()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_checkpoint_updated_at
            BEFORE UPDATE ON projection_checkpoints
            FOR EACH ROW
            EXECUTE FUNCTION update_checkpoint_timestamp();
    """)

    # ==========================================================================
    # Dead Letter Queue Table - Failed event processing storage
    # ==========================================================================
    op.create_table(
        "dead_letter_queue",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("projection_name", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(255), nullable=False),
        sa.Column("event_data", postgresql.JSONB(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("error_stacktrace", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "first_failed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "last_failed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), server_default="failed", nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(255), nullable=True),
        sa.CheckConstraint(
            "status IN ('failed', 'retrying', 'resolved')", name="chk_dlq_status"
        ),
        sa.UniqueConstraint("event_id", "projection_name", name="uq_dlq_event_projection"),
    )

    op.create_index("idx_dlq_status", "dead_letter_queue", ["status"])
    op.create_index("idx_dlq_projection_name", "dead_letter_queue", ["projection_name"])
    op.create_index("idx_dlq_event_id", "dead_letter_queue", ["event_id"])
    op.create_index("idx_dlq_first_failed_at", "dead_letter_queue", ["first_failed_at"])
    op.create_index(
        "idx_dlq_projection_status", "dead_letter_queue", ["projection_name", "status"]
    )
    op.create_index(
        "idx_dlq_active_failures",
        "dead_letter_queue",
        ["first_failed_at"],
        postgresql_where=sa.text("status IN ('failed', 'retrying')"),
    )

    # ==========================================================================
    # Snapshots Table - Aggregate state snapshots for performance
    # ==========================================================================
    op.create_table(
        "snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aggregate_type", sa.String(255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("state", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "aggregate_id", "aggregate_type", name="uq_snapshots_aggregate"
        ),
    )

    op.create_index(
        "idx_snapshots_aggregate_lookup",
        "snapshots",
        ["aggregate_id", "aggregate_type"],
    )
    op.create_index("idx_snapshots_aggregate_type", "snapshots", ["aggregate_type"])
    op.create_index(
        "idx_snapshots_schema_version",
        "snapshots",
        ["aggregate_type", "schema_version"],
    )
    op.create_index("idx_snapshots_created_at", "snapshots", ["created_at"])


def downgrade() -> None:
    """
    Drop event sourcing infrastructure tables.
    """
    # Drop DLQ table
    op.drop_index("idx_dlq_active_failures", table_name="dead_letter_queue")
    op.drop_index("idx_dlq_projection_status", table_name="dead_letter_queue")
    op.drop_index("idx_dlq_first_failed_at", table_name="dead_letter_queue")
    op.drop_index("idx_dlq_event_id", table_name="dead_letter_queue")
    op.drop_index("idx_dlq_projection_name", table_name="dead_letter_queue")
    op.drop_index("idx_dlq_status", table_name="dead_letter_queue")
    op.drop_table("dead_letter_queue")

    # Drop checkpoints table
    op.execute("DROP TRIGGER IF EXISTS trg_checkpoint_updated_at ON projection_checkpoints")
    op.execute("DROP FUNCTION IF EXISTS update_checkpoint_timestamp")
    op.drop_index("idx_checkpoints_global_position", table_name="projection_checkpoints")
    op.drop_index("idx_checkpoints_updated_at", table_name="projection_checkpoints")
    op.drop_index("idx_checkpoints_last_processed", table_name="projection_checkpoints")
    op.drop_table("projection_checkpoints")

    # Drop outbox table
    op.drop_index("idx_outbox_tenant_id", table_name="event_outbox")
    op.drop_index("idx_outbox_event_id", table_name="event_outbox")
    op.drop_index("idx_outbox_pending", table_name="event_outbox")
    op.drop_index("idx_outbox_status_created", table_name="event_outbox")
    op.drop_table("event_outbox")

    # Drop snapshots table
    op.drop_index("idx_snapshots_created_at", table_name="snapshots")
    op.drop_index("idx_snapshots_schema_version", table_name="snapshots")
    op.drop_index("idx_snapshots_aggregate_type", table_name="snapshots")
    op.drop_index("idx_snapshots_aggregate_lookup", table_name="snapshots")
    op.drop_table("snapshots")

    # Drop events table
    op.drop_index("idx_events_aggregate_version", table_name="events")
    op.drop_index("idx_events_type_tenant_timestamp", table_name="events")
    op.drop_index("idx_events_tenant_id", table_name="events")
    op.drop_index("idx_events_timestamp", table_name="events")
    op.drop_index("idx_events_event_type", table_name="events")
    op.drop_index("idx_events_aggregate_type", table_name="events")
    op.drop_index("idx_events_aggregate_id", table_name="events")
    op.drop_table("events")
