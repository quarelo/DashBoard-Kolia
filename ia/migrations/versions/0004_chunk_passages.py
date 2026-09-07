"""chunk_passages: smaller slices embedded on their own

Chunks are sized for summarising (~2000 tokens), which keeps the number of LLM
calls down. One vector averaged over that much text is too coarse to retrieve a
single fact: asking the chat about prices returned five chunks above the
similarity threshold and none of the four that actually mention R$. Passages give
the search something small enough to point at; the chunk stays whole for the
summary. Measured cost: +7% on the embedding phase, which is +0.6% of a run.

Revision ID: 0004
Revises: 0003
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import UUID

from src.app.core.config import settings

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chunk_passages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        # Deleting a chunk takes its passages with it, as it already does for chunks
        # under an analysis.
        sa.Column("chunk_id", UUID(as_uuid=True),
                  sa.ForeignKey("ai.meeting_chunks.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("analysis_id", UUID(as_uuid=True), nullable=False),
        sa.Column("passage_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(settings.embedding_dim), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        # Indexing is re-entrant by design — the worker recovers an unfinished
        # analysis on startup — so two runners can both see a chunk as unindexed.
        # Observed exactly that: every passage inserted twice. The constraint makes
        # the second insert fail instead of silently doubling the index.
        sa.UniqueConstraint("chunk_id", "passage_index",
                            name="chunk_passages_chunk_passage_key"),
        schema="ai",
    )
    op.create_index("ix_ai_chunk_passages_chunk_id", "chunk_passages",
                    ["chunk_id"], schema="ai")
    # Every search is scoped to one analysis, so this is the filter that runs first.
    op.create_index("ix_ai_chunk_passages_analysis_id", "chunk_passages",
                    ["analysis_id"], schema="ai")


def downgrade() -> None:
    op.drop_table("chunk_passages", schema="ai")
