"""Add source_metadata JSONB to meeting_analyses for business context enrichment.

The backend already stores all CSV metadata in core.meetings.source_metadata.
This column carries the subset relevant to analysis (TP_RECURSO, NOME_SEGMENTO,
FAIXA_FATURAMENTO_CLIENTE_EC, NOTA_NPS, DURACAO_MEETING) into the IA schema so
the worker — which runs asynchronously without the original request — can inject
business context into chunk and consolidation prompts.

Revision ID: 0007
Revises: 0006
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "meeting_analyses",
        sa.Column("source_metadata", sa.dialects.postgresql.JSONB(), nullable=True),
        schema="ai",
    )


def downgrade() -> None:
    op.drop_column("meeting_analyses", "source_metadata", schema="ai")
