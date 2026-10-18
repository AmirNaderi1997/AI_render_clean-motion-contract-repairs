"""add durable video studio conversations, projects, actions and events

Revision ID: fe91d3a70c42
Revises: a9e3f6c21d47
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "fe91d3a70c42"
down_revision: Union[str, Sequence[str], None] = "a9e3f6c21d47"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "studio_conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_key", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("status_voice_enabled", sa.Boolean(), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_studio_conversations_user_key", "studio_conversations", ["user_key"])
    op.create_table(
        "studio_messages",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("studio_conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("attachments", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_studio_messages_conversation_id", "studio_messages", ["conversation_id"])
    op.create_table(
        "studio_attachments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("studio_conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_key", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("path", sa.String(1000), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_studio_attachments_conversation_id", "studio_attachments", ["conversation_id"])
    op.create_index("ix_studio_attachments_user_key", "studio_attachments", ["user_key"])
    op.create_table(
        "studio_projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("studio_conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_key", sa.String(64), nullable=False),
        sa.Column("engine", sa.String(32), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("external_ref", sa.String(64), nullable=True),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_studio_projects_conversation_id", "studio_projects", ["conversation_id"])
    op.create_index("ix_studio_projects_user_key", "studio_projects", ["user_key"])
    op.create_table(
        "studio_project_versions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("studio_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "version", name="uq_studio_project_version"),
    )
    op.create_index("ix_studio_project_versions_project_id", "studio_project_versions", ["project_id"])
    op.create_table(
        "studio_actions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("studio_conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("studio_projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_studio_actions_conversation_id", "studio_actions", ["conversation_id"])
    op.create_index("ix_studio_actions_project_id", "studio_actions", ["project_id"])
    op.create_table(
        "studio_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("studio_conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("conversation_id", "seq", name="uq_studio_event_seq"),
    )
    op.create_index("ix_studio_events_conversation_id", "studio_events", ["conversation_id"])


def downgrade() -> None:
    for table in ("studio_events", "studio_actions", "studio_project_versions", "studio_projects", "studio_attachments", "studio_messages"):
        op.drop_table(table)
    op.drop_table("studio_conversations")
