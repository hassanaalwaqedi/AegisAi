"""Add durable event correlation incidents.

Revision ID: 20260802_03
Revises: 20260802_02
Create Date: 2026-08-02
"""

from alembic import op
import sqlalchemy as sa


revision = "20260802_03"
down_revision = "20260802_02"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _column_names(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    return {
        str(index.get("name"))
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
        if index.get("name")
    }


def _create_index_if_missing(name: str, table_name: str, columns: list[str]) -> None:
    if name not in _index_names(table_name):
        op.create_index(name, table_name, columns)


def upgrade() -> None:
    if "incidents" not in _table_names():
        op.create_table(
            "incidents",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("incident_id", sa.String(length=128), nullable=False),
            sa.Column("camera_id", sa.String(length=80), nullable=False),
            sa.Column("primary_track_id", sa.String(length=160), nullable=True),
            sa.Column("related_track_ids", sa.JSON(), nullable=False),
            sa.Column("zone_id", sa.String(length=120), nullable=True),
            sa.Column("zone_name", sa.String(length=160), nullable=True),
            sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_seen_time", sa.DateTime(timezone=True), nullable=False),
            sa.Column("current_risk_level", sa.String(length=20), nullable=True),
            sa.Column("max_risk_score", sa.Float(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("event_ids", sa.JSON(), nullable=False),
            sa.Column("alert_ids", sa.JSON(), nullable=False),
            sa.Column("evidence_ids", sa.JSON(), nullable=False),
            sa.Column("summary_reason", sa.Text(), nullable=True),
            sa.Column("contributing_factors", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("status IN ('active', 'resolved')", name="ck_incidents_status"),
            sa.UniqueConstraint("incident_id", name="uq_incidents_incident_id"),
        )
    for name, columns in (
        ("ix_incidents_incident_id", ["incident_id"]),
        ("ix_incidents_camera_id", ["camera_id"]),
        ("ix_incidents_primary_track_id", ["primary_track_id"]),
        ("ix_incidents_zone_id", ["zone_id"]),
        ("ix_incidents_last_seen_time", ["last_seen_time"]),
        ("ix_incidents_status", ["status"]),
        ("ix_incidents_active_recent", ["status", "camera_id", "last_seen_time"]),
    ):
        _create_index_if_missing(name, "incidents", columns)
    if "incident_id" not in _column_names("events"):
        op.add_column("events", sa.Column("incident_id", sa.String(length=128), nullable=True))
    _create_index_if_missing("ix_events_incident_id", "events", ["incident_id"])


def downgrade() -> None:
    op.drop_index("ix_events_incident_id", table_name="events")
    op.drop_column("events", "incident_id")

    op.drop_index("ix_incidents_active_recent", table_name="incidents")
    op.drop_index("ix_incidents_status", table_name="incidents")
    op.drop_index("ix_incidents_last_seen_time", table_name="incidents")
    op.drop_index("ix_incidents_zone_id", table_name="incidents")
    op.drop_index("ix_incidents_primary_track_id", table_name="incidents")
    op.drop_index("ix_incidents_camera_id", table_name="incidents")
    op.drop_index("ix_incidents_incident_id", table_name="incidents")
    op.drop_table("incidents")
