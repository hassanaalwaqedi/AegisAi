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


def upgrade() -> None:
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
    op.create_index("ix_system_knowledge_key", "system_knowledge", ["key"])
    op.create_index("ix_system_knowledge_category", "system_knowledge", ["category"])
    op.create_index("ix_system_knowledge_visibility", "system_knowledge", ["visibility"])
    op.create_index("ix_system_knowledge_is_active", "system_knowledge", ["is_active"])
    op.create_index("ix_system_knowledge_retrieval", "system_knowledge", ["category", "visibility", "is_active"])

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
    op.create_index("ix_system_knowledge_audit_record_id", "system_knowledge_audit", ["record_id"])
    op.create_index("ix_system_knowledge_audit_key", "system_knowledge_audit", ["key"])
    op.create_index("ix_system_knowledge_audit_record_created", "system_knowledge_audit", ["record_id", "created_at"])


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
