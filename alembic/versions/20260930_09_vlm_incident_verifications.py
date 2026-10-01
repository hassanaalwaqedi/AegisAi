"""Store secondary Gemini visual incident verification results."""

from alembic import op
import sqlalchemy as sa


revision = "20260930_09"
down_revision = "20260918_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "incident_verifications" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "incident_verifications",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("verification_id", sa.String(160), nullable=False),
        sa.Column("incident_id", sa.String(128), nullable=False),
        sa.Column("event_id", sa.String(128), nullable=False),
        sa.Column("camera_id", sa.String(80), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False, server_default="gemini"),
        sa.Column("model", sa.String(200)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("combined_state", sa.String(20)),
        sa.Column("verdict", sa.String(64)),
        sa.Column("confidence", sa.Float()),
        sa.Column("severity", sa.String(20)),
        sa.Column("summary", sa.Text()),
        sa.Column("subjects", sa.JSON(), nullable=False),
        sa.Column("observations", sa.JSON(), nullable=False),
        sa.Column("supporting_evidence", sa.JSON(), nullable=False),
        sa.Column("contradicting_evidence", sa.JSON(), nullable=False),
        sa.Column("uncertainties", sa.JSON(), nullable=False),
        sa.Column("recommended_action", sa.String(32)),
        sa.Column("evidence_metadata", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("latency_ms", sa.Float()),
        sa.Column("analysis_version", sa.String(64), nullable=False, server_default="vlm-incident-v1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("verification_id", name="uq_incident_verifications_verification_id"),
    )
    op.create_index("ix_incident_verifications_verification_id", "incident_verifications", ["verification_id"], unique=True)
    op.create_index("ix_incident_verifications_incident_id", "incident_verifications", ["incident_id"])
    op.create_index("ix_incident_verifications_event_id", "incident_verifications", ["event_id"])
    op.create_index("ix_incident_verifications_camera_id", "incident_verifications", ["camera_id"])
    op.create_index("ix_incident_verifications_status", "incident_verifications", ["status"])
    op.create_index("ix_incident_verifications_incident_created", "incident_verifications", ["incident_id", "created_at"])


def downgrade() -> None:
    op.drop_table("incident_verifications")
