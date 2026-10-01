"""Allow event-level VLM verification before incident promotion."""

from alembic import op
import sqlalchemy as sa


revision = "20260930_10"
down_revision = "20260930_09"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep the existing verification table and records; an event_id remains
    # mandatory while incident_id becomes an optional promotion association.
    with op.batch_alter_table("incident_verifications") as batch_op:
        batch_op.alter_column(
            "incident_id",
            existing_type=sa.String(length=128),
            nullable=True,
        )
        batch_op.alter_column(
            "combined_state",
            existing_type=sa.String(length=20),
            type_=sa.String(length=32),
            nullable=True,
        )


def downgrade() -> None:
    # The downgrade is naturally valid only before event-only candidate rows
    # have been written; it must not fabricate incident identifiers for them.
    with op.batch_alter_table("incident_verifications") as batch_op:
        batch_op.alter_column(
            "incident_id",
            existing_type=sa.String(length=128),
            nullable=False,
        )
        batch_op.alter_column(
            "combined_state",
            existing_type=sa.String(length=32),
            type_=sa.String(length=20),
            nullable=True,
        )
