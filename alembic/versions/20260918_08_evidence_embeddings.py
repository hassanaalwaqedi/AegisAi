"""Add rebuildable multilingual evidence vectors without modifying events."""
from alembic import op
import sqlalchemy as sa

revision = "20260918_08"
down_revision = "20260916_07"
branch_labels = None
depends_on = None


def upgrade():
    if "evidence_embeddings" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "evidence_embeddings",
        sa.Column("event_id", sa.String(128), primary_key=True),
        sa.Column("model_key", sa.String(200), primary_key=True),
        sa.Column("document_hash", sa.String(64), nullable=False),
        sa.Column("vector", sa.JSON(), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("evidence_embeddings")
