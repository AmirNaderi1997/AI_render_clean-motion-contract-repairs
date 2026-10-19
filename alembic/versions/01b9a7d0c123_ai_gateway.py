"""Add AI gateway catalog, routing, settings and request logs."""
from alembic import op
import sqlalchemy as sa

revision = "01b9a7d0c123"
down_revision = "fe91d3a70c42"
branch_labels = None
depends_on = None


def upgrade():
    for name, size in (("ai_models", 512), ("ai_model_routes", 64), ("ai_gateway_settings", 64)):
        op.create_table(name, sa.Column("key", sa.String(size), primary_key=True),
                        sa.Column("data", sa.JSON(), nullable=False))
    op.create_table("ai_request_logs", sa.Column("id", sa.String(36), primary_key=True),
                    sa.Column("created_at", sa.String(40), nullable=False),
                    sa.Column("route", sa.String(64), nullable=False),
                    sa.Column("user_id", sa.String(64), nullable=True),
                    sa.Column("job_id", sa.String(64), nullable=True),
                    sa.Column("status", sa.String(32), nullable=False),
                    sa.Column("model", sa.String(512), nullable=False),
                    sa.Column("data", sa.JSON(), nullable=False))
    for column in ("created_at", "route", "user_id", "job_id", "status", "model"):
        op.create_index(f"ix_ai_request_logs_{column}", "ai_request_logs", [column])


def downgrade():
    op.drop_table("ai_request_logs")
    for table in ("ai_gateway_settings", "ai_model_routes", "ai_models"):
        op.drop_table(table)
