"""Add durable operator alert lifecycle records.

Revision ID: 20260809_04
Revises: 20260802_03
Create Date: 2026-08-09
"""

from alembic import op
import sqlalchemy as sa


revision = "20260809_04"
down_revision = "20260802_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Local/dev startup also calls SQLAlchemy ``create_all`` so early installs
    # can legitimately have this additive table before Alembic has recorded
    # this revision.  Treat that schema as already upgraded instead of making
    # the next deployment fail on an existing table.
    if "operational_alerts" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "operational_alerts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("alert_id", sa.String(length=128), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("event_record_id", sa.Integer(), sa.ForeignKey("events.id"), nullable=True),
        sa.Column("track_id", sa.String(length=160), nullable=True),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("zone", sa.String(length=160), nullable=True),
        sa.Column("factors", sa.JSON(), nullable=False),
        sa.Column("cooldown_key", sa.String(length=300), nullable=True),
        sa.Column("cooldown_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.String(length=100), nullable=True),
        sa.Column("delivery_status", sa.String(length=32), nullable=False, server_default="created"),
        sa.Column("delivery_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_delivery_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("alert_id", name="uq_operational_alerts_alert_id"),
    )
    op.create_index("ix_operational_alerts_alert_id", "operational_alerts", ["alert_id"])
    op.create_index("ix_operational_alerts_event_id", "operational_alerts", ["event_id"])
    op.create_index("ix_operational_alerts_event_record_id", "operational_alerts", ["event_record_id"])
    op.create_index("ix_operational_alerts_track_id", "operational_alerts", ["track_id"])
    op.create_index("ix_operational_alerts_level", "operational_alerts", ["level"])
    op.create_index("ix_operational_alerts_acknowledged", "operational_alerts", ["acknowledged"])
    op.create_index("ix_operational_alerts_delivery_status", "operational_alerts", ["delivery_status"])
    op.create_index("ix_operational_alerts_cooldown_key", "operational_alerts", ["cooldown_key"])
    op.create_index("ix_operational_alerts_cooldown_expires_at", "operational_alerts", ["cooldown_expires_at"])
    op.create_index("ix_operational_alerts_active_recent", "operational_alerts", ["acknowledged", "created_at"])
    op.create_index("ix_operational_alerts_cooldown", "operational_alerts", ["cooldown_key", "cooldown_expires_at"])


def downgrade() -> None:
    for name in (
        "ix_operational_alerts_cooldown",
        "ix_operational_alerts_active_recent",
        "ix_operational_alerts_cooldown_expires_at",
        "ix_operational_alerts_cooldown_key",
        "ix_operational_alerts_delivery_status",
        "ix_operational_alerts_acknowledged",
        "ix_operational_alerts_level",
        "ix_operational_alerts_track_id",
        "ix_operational_alerts_event_record_id",
        "ix_operational_alerts_event_id",
        "ix_operational_alerts_alert_id",
    ):
        op.drop_index(name, table_name="operational_alerts")
    op.drop_table("operational_alerts")
