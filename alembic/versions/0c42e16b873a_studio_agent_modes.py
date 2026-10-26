"""Add selectable agents; existing requests remain Lite.

Revision ID: 0c42e16b873a
Revises: 01b9a7d0c123
"""
from alembic import op
import sqlalchemy as sa

revision = "0c42e16b873a"
down_revision = "01b9a7d0c123"
branch_labels = depends_on = None


def upgrade():
    op.add_column("studio_messages", sa.Column("agent_mode", sa.String(16), nullable=False, server_default="lite"))
    op.create_table("studio_agent_preferences", sa.Column("user_key", sa.String(64), primary_key=True),
                    sa.Column("default_mode", sa.String(16), nullable=False))
    op.create_table("studio_agent_runs", sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("studio_conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_key", sa.String(64), nullable=False), sa.Column("message_id", sa.String(64), nullable=False),
        sa.Column("agent_mode", sa.String(16), nullable=False), sa.Column("status", sa.String(32), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("conversation_id", "message_id", name="uq_studio_agent_message"))
    op.create_index("ix_studio_agent_runs_conversation_id", "studio_agent_runs", ["conversation_id"])
    op.create_index("ix_studio_agent_runs_user_key", "studio_agent_runs", ["user_key"])


def downgrade():
    op.drop_table("studio_agent_runs")
    op.drop_table("studio_agent_preferences")
    op.drop_column("studio_messages", "agent_mode")
