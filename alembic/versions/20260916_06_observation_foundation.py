"""Add append-only camera observations before incident assessment.

Revision ID: 20260916_06
Revises: 20260810_05
Create Date: 2026-09-16
"""

from alembic import op
import sqlalchemy as sa


revision = "20260916_06"
down_revision = "20260810_05"
branch_labels = None
depends_on = None


def _index_names(table_name: str) -> set[str]:
    return {
        str(index.get("name"))
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
        if index.get("name")
    }


def _create_index_if_missing(
    name: str,
    table_name: str,
    columns: list[str],
    *,
    unique: bool = False,
) -> None:
    if name not in _index_names(table_name):
        op.create_index(name, table_name, columns, unique=unique)


def upgrade() -> None:
    if "observations" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "observations",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("observation_id", sa.String(length=160), nullable=False),
            sa.Column("schema_version", sa.String(length=16), nullable=False, server_default="1.0"),
            sa.Column("camera_id", sa.String(length=80), nullable=False),
            sa.Column("source_epoch", sa.String(length=64), nullable=False),
            sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("frame_id", sa.Integer(), nullable=False),
            sa.Column("track_key", sa.String(length=160), nullable=True),
            sa.Column("related_track_key", sa.String(length=160), nullable=True),
            sa.Column("observation_type", sa.String(length=64), nullable=False),
            sa.Column("label", sa.String(length=100), nullable=False),
            sa.Column("model_confidence", sa.Float(), nullable=True),
            sa.Column("bounding_box", sa.JSON(), nullable=True),
            sa.Column("zone_id", sa.String(length=120), nullable=True),
            sa.Column("zone_name", sa.String(length=160), nullable=True),
            sa.Column("event_id", sa.String(length=128), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("observation_id", name="uq_observations_observation_id"),
        )
    for name, columns, unique in (
        ("ix_observations_observation_id", ["observation_id"], True),
        ("ix_observations_camera_id", ["camera_id"], False),
        ("ix_observations_source_epoch", ["source_epoch"], False),
        ("ix_observations_captured_at", ["captured_at"], False),
        ("ix_observations_track_key", ["track_key"], False),
        ("ix_observations_related_track_key", ["related_track_key"], False),
        ("ix_observations_observation_type", ["observation_type"], False),
        ("ix_observations_zone_id", ["zone_id"], False),
        ("ix_observations_event_id", ["event_id"], False),
        ("ix_observations_camera_epoch_frame", ["camera_id", "source_epoch", "frame_id"], False),
        ("ix_observations_track_time", ["track_key", "captured_at"], False),
    ):
        _create_index_if_missing(name, "observations", columns, unique=unique)


def downgrade() -> None:
    for name in (
        "ix_observations_track_time",
        "ix_observations_camera_epoch_frame",
        "ix_observations_event_id",
        "ix_observations_zone_id",
        "ix_observations_observation_type",
        "ix_observations_related_track_key",
        "ix_observations_track_key",
        "ix_observations_captured_at",
        "ix_observations_source_epoch",
        "ix_observations_camera_id",
        "ix_observations_observation_id",
    ):
        if name in _index_names("observations"):
            op.drop_index(name, table_name="observations")
    op.drop_table("observations")
