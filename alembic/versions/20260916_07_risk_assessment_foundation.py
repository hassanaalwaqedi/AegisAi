"""Add versioned explainable incident risk assessments.

Revision ID: 20260916_07
Revises: 20260916_06
Create Date: 2026-09-16
"""

from alembic import op
import sqlalchemy as sa


revision = "20260916_07"
down_revision = "20260916_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "risk_assessments" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "risk_assessments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("assessment_id", sa.String(length=160), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False, server_default="1.0"),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("incident_id", sa.String(length=128), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("risk_level", sa.String(length=20), nullable=False),
        sa.Column("policy_score", sa.Float(), nullable=True),
        sa.Column("confidence_status", sa.String(length=32), nullable=False, server_default="not_calibrated"),
        sa.Column("factor_results", sa.JSON(), nullable=False),
        sa.Column("missing_evidence", sa.JSON(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("assessment_id", name="uq_risk_assessments_assessment_id"),
    )
    op.create_index("ix_risk_assessments_assessment_id", "risk_assessments", ["assessment_id"], unique=True)
    op.create_index("ix_risk_assessments_incident_id", "risk_assessments", ["incident_id"])
    op.create_index("ix_risk_assessments_event_id", "risk_assessments", ["event_id"])
    op.create_index("ix_risk_assessments_assessed_at", "risk_assessments", ["assessed_at"])
    op.create_index("ix_risk_assessments_incident_time", "risk_assessments", ["incident_id", "assessed_at"])


def downgrade() -> None:
    op.drop_table("risk_assessments")
