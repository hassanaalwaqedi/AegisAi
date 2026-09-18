"""Add versioned database-backed official system knowledge.

Revision ID: 20260731_01
Revises:
Create Date: 2026-07-31
"""

from alembic import op
import sqlalchemy as sa


revision = "20260731_01"
down_revision = None
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


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
    tables = _table_names()
    # The project historically used ``Base.metadata.create_all`` and init.sql
    # before it adopted Alembic.  A fresh Alembic installation therefore needs
    # the original core schema, while an existing local database must not fail
    # because that schema is already present.
    if "events" not in tables:
        op.create_table(
            "events",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("event_type", sa.String(length=50), nullable=False),
            sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
            sa.Column("track_id", sa.Integer(), nullable=True),
            sa.Column("risk_level", sa.String(length=20), nullable=True),
            sa.Column("risk_score", sa.Float(), nullable=True),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("factors", sa.JSON(), nullable=True),
            sa.Column("zone", sa.String(length=50), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "alerts" not in tables:
        op.create_table(
            "alerts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id"), nullable=False),
            sa.Column("level", sa.String(length=20), nullable=False),
            sa.Column("acknowledged", sa.Boolean(), nullable=True),
            sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("acknowledged_by", sa.String(length=100), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "track_stats" not in tables:
        op.create_table(
            "track_stats",
            sa.Column("track_id", sa.Integer(), primary_key=True),
            sa.Column("class_name", sa.String(length=50), nullable=False),
            sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
            sa.Column("total_frames", sa.Integer(), nullable=True),
            sa.Column("max_risk_score", sa.Float(), nullable=True),
            sa.Column("behaviors_detected", sa.JSON(), nullable=True),
        )
    if "sessions" not in tables:
        op.create_table(
            "sessions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
            sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
            sa.Column("total_frames", sa.Integer(), nullable=True),
            sa.Column("total_detections", sa.Integer(), nullable=True),
            sa.Column("total_tracks", sa.Integer(), nullable=True),
            sa.Column("total_alerts", sa.Integer(), nullable=True),
            sa.Column("avg_fps", sa.Float(), nullable=True),
        )
    if "system_knowledge" not in tables:
        op.create_table(
            "system_knowledge",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("key", sa.String(length=160), nullable=False),
            sa.Column("category", sa.String(length=64), nullable=False),
            sa.Column("title", sa.String(length=300), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("content_ar", sa.Text(), nullable=True),
            sa.Column("content_en", sa.Text(), nullable=True),
            sa.Column("content_tr", sa.Text(), nullable=True),
            sa.Column("structured_data", sa.JSON(), nullable=False),
            sa.Column("visibility", sa.String(length=16), nullable=False),
            sa.Column("priority", sa.Integer(), nullable=False),
            sa.Column("source", sa.String(length=300), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("created_by", sa.String(length=160), nullable=True),
            sa.Column("updated_by", sa.String(length=160), nullable=True),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("visibility IN ('public', 'private')", name="ck_system_knowledge_visibility"),
            sa.CheckConstraint(
                "category IN ('creator_profile', 'creator_contributions', 'project_profile', "
                "'project_purpose', 'project_architecture', 'project_capabilities', "
                "'project_technology', 'project_security', 'project_limitations')",
                name="ck_system_knowledge_category",
            ),
            sa.CheckConstraint("priority >= 0 AND priority <= 1000", name="ck_system_knowledge_priority"),
            sa.CheckConstraint("version >= 1", name="ck_system_knowledge_version"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("key", "version", name="uq_system_knowledge_key_version"),
        )
    for name, columns in (
        ("ix_system_knowledge_key", ["key"]),
        ("ix_system_knowledge_category", ["category"]),
        ("ix_system_knowledge_visibility", ["visibility"]),
        ("ix_system_knowledge_is_active", ["is_active"]),
        ("ix_system_knowledge_retrieval", ["category", "visibility", "is_active"]),
    ):
        _create_index_if_missing(name, "system_knowledge", columns)
    if "system_knowledge_audit" not in tables:
        op.create_table(
            "system_knowledge_audit",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("record_id", sa.Uuid(), nullable=False),
            sa.Column("key", sa.String(length=160), nullable=False),
            sa.Column("action", sa.String(length=32), nullable=False),
            sa.Column("actor", sa.String(length=160), nullable=False),
            sa.Column("before", sa.JSON(), nullable=True),
            sa.Column("after", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["record_id"], ["system_knowledge.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    for name, columns in (
        ("ix_system_knowledge_audit_record_id", ["record_id"]),
        ("ix_system_knowledge_audit_key", ["key"]),
        ("ix_system_knowledge_audit_record_created", ["record_id", "created_at"]),
    ):
        _create_index_if_missing(name, "system_knowledge_audit", columns)


def downgrade() -> None:
    op.drop_index("ix_system_knowledge_audit_record_created", table_name="system_knowledge_audit")
    op.drop_index("ix_system_knowledge_audit_key", table_name="system_knowledge_audit")
    op.drop_index("ix_system_knowledge_audit_record_id", table_name="system_knowledge_audit")
    op.drop_table("system_knowledge_audit")
    op.drop_index("ix_system_knowledge_retrieval", table_name="system_knowledge")
    op.drop_index("ix_system_knowledge_is_active", table_name="system_knowledge")
    op.drop_index("ix_system_knowledge_visibility", table_name="system_knowledge")
    op.drop_index("ix_system_knowledge_category", table_name="system_knowledge")
    op.drop_index("ix_system_knowledge_key", table_name="system_knowledge")
    op.drop_table("system_knowledge")
