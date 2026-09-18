"""Add durable evidence fields to risk events.

Revision ID: 20260802_02
Revises: 20260731_01
Create Date: 2026-08-02
"""

from alembic import op
import sqlalchemy as sa


revision = "20260802_02"
down_revision = "20260731_01"
branch_labels = None
depends_on = None


def _column_names(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    return {
        str(index.get("name"))
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
        if index.get("name")
    }


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if column.name not in _column_names(table_name):
        op.add_column(table_name, column)


def _create_index_if_missing(name: str, table_name: str, columns: list[str], *, unique: bool = False) -> None:
    if name not in _index_names(table_name):
        op.create_index(name, table_name, columns, unique=unique)


def upgrade() -> None:
    for column in (
        sa.Column("event_id", sa.String(length=128), nullable=True),
        sa.Column("alert_id", sa.String(length=128), nullable=True),
        sa.Column("track_key", sa.String(length=160), nullable=True),
        sa.Column("camera_id", sa.String(length=80), nullable=True),
        sa.Column("camera_name", sa.String(length=160), nullable=True),
        sa.Column("object_class", sa.String(length=100), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("zone_id", sa.String(length=120), nullable=True),
        sa.Column("zone_name", sa.String(length=160), nullable=True),
        sa.Column("bounding_box", sa.JSON(), nullable=True),
        sa.Column("snapshot_path", sa.String(length=512), nullable=True),
        sa.Column("snapshot_status", sa.String(length=20), nullable=False, server_default="unavailable"),
        sa.Column("clip_path", sa.String(length=512), nullable=True),
    ):
        _add_column_if_missing("events", column)
    _create_index_if_missing("ix_events_event_id", "events", ["event_id"], unique=True)
    _create_index_if_missing("ix_events_alert_id", "events", ["alert_id"])
    _create_index_if_missing("ix_events_track_key", "events", ["track_key"])
    _create_index_if_missing("ix_events_camera_id", "events", ["camera_id"])
    _create_index_if_missing("ix_events_evidence_recent", "events", ["risk_level", "timestamp"])


def downgrade() -> None:
    op.drop_index("ix_events_evidence_recent", table_name="events")
    op.drop_index("ix_events_camera_id", table_name="events")
    op.drop_index("ix_events_track_key", table_name="events")
    op.drop_index("ix_events_alert_id", table_name="events")
    op.drop_index("ix_events_event_id", table_name="events")

    op.drop_column("events", "clip_path")
    op.drop_column("events", "snapshot_status")
    op.drop_column("events", "snapshot_path")
    op.drop_column("events", "bounding_box")
    op.drop_column("events", "zone_name")
    op.drop_column("events", "zone_id")
    op.drop_column("events", "reason")
    op.drop_column("events", "object_class")
    op.drop_column("events", "camera_name")
    op.drop_column("events", "camera_id")
    op.drop_column("events", "track_key")
    op.drop_column("events", "alert_id")
    op.drop_column("events", "event_id")
