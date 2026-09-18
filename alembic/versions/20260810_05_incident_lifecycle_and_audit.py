"""Add incident lifecycle decisions and durable operational audit logs.

Revision ID: 20260810_05
Revises: 20260809_04
Create Date: 2026-08-10
"""

from alembic import op
import sqlalchemy as sa


revision = "20260810_05"
down_revision = "20260809_04"
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


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if column.name not in _column_names(table_name):
        op.add_column(table_name, column)


def _create_index_if_missing(name: str, table_name: str, columns: list[str]) -> None:
    if name not in _index_names(table_name):
        op.create_index(name, table_name, columns)


def upgrade() -> None:
    for column in (
        sa.Column("lifecycle_status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("lifecycle_updated_by", sa.String(length=160), nullable=True),
        sa.Column("lifecycle_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lifecycle_reason", sa.Text(), nullable=True),
        sa.Column("risk_types", sa.JSON(), nullable=True),
    ):
        _add_column_if_missing("incidents", column)
    op.execute("UPDATE incidents SET lifecycle_status = CASE WHEN status = 'resolved' THEN 'resolved' ELSE 'open' END")
    _create_index_if_missing("ix_incidents_lifecycle_status", "incidents", ["lifecycle_status"])

    if "audit_logs" not in _table_names():
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("action", sa.String(length=96), nullable=False),
            sa.Column("actor_id", sa.String(length=160), nullable=True),
            sa.Column("resource_type", sa.String(length=64), nullable=True),
            sa.Column("resource_id", sa.String(length=160), nullable=True),
            sa.Column("details", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    for name, columns in (
        ("ix_audit_logs_action", ["action"]),
        ("ix_audit_logs_actor_id", ["actor_id"]),
        ("ix_audit_logs_resource_type", ["resource_type"]),
        ("ix_audit_logs_resource_id", ["resource_id"]),
        ("ix_audit_logs_created_at", ["created_at"]),
        ("ix_audit_logs_resource_recent", ["resource_type", "resource_id", "created_at"]),
        ("ix_audit_logs_action_recent", ["action", "created_at"]),
    ):
        _create_index_if_missing(name, "audit_logs", columns)


def downgrade() -> None:
    for name in (
        "ix_audit_logs_action_recent",
        "ix_audit_logs_resource_recent",
        "ix_audit_logs_created_at",
        "ix_audit_logs_resource_id",
        "ix_audit_logs_resource_type",
        "ix_audit_logs_actor_id",
        "ix_audit_logs_action",
    ):
        op.drop_index(name, table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_incidents_lifecycle_status", table_name="incidents")
    op.drop_column("incidents", "risk_types")
    op.drop_column("incidents", "lifecycle_reason")
    op.drop_column("incidents", "lifecycle_updated_at")
    op.drop_column("incidents", "lifecycle_updated_by")
    op.drop_column("incidents", "lifecycle_status")
