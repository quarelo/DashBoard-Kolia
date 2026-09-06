"""full-text index on passages, for hybrid retrieval

Vector search alone matches on topic, so a passage naming a price loses to one
about "leads" and "ticket médio" — asked about values, the priced passage did not
reach the top ten. Lexical search alone has the opposite failure: it ranks by term
frequency, so "concorrente" retrieved "trabalhei em algumas empresas". The two
miss different things, which is why both run and the results are fused.

The column is generated and indexed so the query stays a plain @@ match; no
application code has to keep it in sync.

Revision ID: 0005
Revises: 0004
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE ai.chunk_passages
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (to_tsvector('portuguese', content)) STORED
    """)
    op.execute("""
        CREATE INDEX ix_ai_chunk_passages_search
        ON ai.chunk_passages USING GIN (search_vector)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ai.ix_ai_chunk_passages_search")
    op.execute("ALTER TABLE ai.chunk_passages DROP COLUMN IF EXISTS search_vector")
