"""initial schema: meeting analyses and their chunks

The shape the database had before the progressive-summary columns. A database
that predates Alembic looks like this, so it can be adopted with
`alembic stamp 0001` rather than rebuilt.

Revision ID: 0001
Revises:
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB, UUID

from src.app.core.config import settings

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS ai")
    # Vector columns cannot be created before the extension exists.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "meeting_analyses",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("external_meeting_id", UUID(as_uuid=True), nullable=False),
        sa.Column("external_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("total_chunks", sa.Integer(), nullable=False),
        sa.Column("final_summary", JSONB(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        schema="ai",
    )
    op.create_index("ix_ai_meeting_analyses_external_meeting_id", "meeting_analyses",
                    ["external_meeting_id"], schema="ai")
    op.create_index("ix_ai_meeting_analyses_external_user_id", "meeting_analyses",
                    ["external_user_id"], schema="ai")
    op.create_index("ix_ai_meeting_analyses_status", "meeting_analyses",
                    ["status"], schema="ai")

    op.create_table(
        "meeting_chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        # Deleting an analysis takes its chunks and their embeddings with it.
        sa.Column("analysis_id", UUID(as_uuid=True),
                  sa.ForeignKey("ai.meeting_analyses.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("external_meeting_id", UUID(as_uuid=True), nullable=False),
        sa.Column("external_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("clean_content", sa.Text(), nullable=True),
        sa.Column("chunk_summary", JSONB(), nullable=True),
        # Dimension comes from settings so the column always matches the embedding
        # model the service is configured to call.
        sa.Column("embedding", Vector(settings.embedding_dim), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        schema="ai",
    )
    op.create_index("ix_ai_meeting_chunks_analysis_id", "meeting_chunks",
                    ["analysis_id"], schema="ai")
    op.create_index("ix_ai_meeting_chunks_external_meeting_id", "meeting_chunks",
                    ["external_meeting_id"], schema="ai")
    op.create_index("ix_ai_meeting_chunks_external_user_id", "meeting_chunks",
                    ["external_user_id"], schema="ai")


def downgrade() -> None:
    op.drop_table("meeting_chunks", schema="ai")
    op.drop_table("meeting_analyses", schema="ai")
