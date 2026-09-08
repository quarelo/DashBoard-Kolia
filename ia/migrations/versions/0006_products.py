"""products: TOTVS catalogue for grounding product identification

Populated once, out-of-band, by ia/scraper/. `source_url` is unique so a rerun
of the loader can be made safe to skip duplicates rather than doubling every
row. The HNSW index is what makes the future "top 5 candidates" similarity
search cheap; cosine matches the distance operator already used for
meeting_chunks.embedding.

Revision ID: 0006
Revises: 0005

Numbered 0006, not 0004: it was written in parallel with 0004_chunk_passages
and 0005_passage_fulltext (the hybrid-search work), both of which also
branched off 0003 and landed on main first. Renumbered after them instead of
keeping 0004, to avoid two revisions claiming the same id.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import UUID

from src.app.core.config import settings

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(settings.embedding_dim), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("source_url", name="products_source_url_key"),
        schema="ai",
    )
    op.create_index(
        "products_embedding_idx", "products", ["embedding"], schema="ai",
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("products_embedding_idx", table_name="products", schema="ai")
    op.drop_table("products", schema="ai")
