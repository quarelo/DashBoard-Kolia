"""chat_messages: a conversa sobrevive ao recarregar a página

Até aqui o histórico existia apenas no `payload` que o navegador reenviava a
cada pergunta, então fechar a aba apagava a conversa inteira. Uma conversa por
reunião: o usuário escolhe a reunião e continua de onde parou, e é por isso que
a chave é `analysis_id` e não um id de sessão.

`ON DELETE CASCADE` porque uma conversa sobre uma análise apagada não tem
sentido nem dono. O índice é por (analysis_id, seq) porque a única leitura
que existe é "a conversa desta reunião, em ordem".

Revision ID: 0008
Revises: 0007
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        # A ordem da conversa não pode depender de `created_at`: `now()` no
        # Postgres é o tempo da TRANSAÇÃO, então pergunta e resposta gravadas no
        # mesmo commit recebem o mesmo instante e o desempate caía no id, que é
        # UUID aleatório — a conversa voltava embaralhada, com a resposta antes da
        # pergunta. Pior, o saneamento do histórico descartava a lista torta
        # inteira e a pergunta seguinte perdia o contexto.
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("analysis_id", UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        # O que o servidor decidiu, guardado junto da mensagem: sem isso uma
        # recusa antiga e uma resposta antiga ficam indistinguíveis ao reabrir a
        # conversa, e foi exatamente essa cegueira que fez o diagnóstico do chat
        # depender de contar tokens no log do Ollama.
        sa.Column("grounded", sa.Boolean(), nullable=True),
        sa.Column("fallback_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint("role in ('user', 'assistant')",
                           name="chat_messages_role_check"),
        sa.ForeignKeyConstraint(["analysis_id"], ["ai.meeting_analyses.id"],
                                ondelete="CASCADE"),
        schema="ai",
    )
    op.create_index(
        "chat_messages_analysis_seq_idx", "chat_messages",
        ["analysis_id", "seq"], schema="ai",
    )


def downgrade() -> None:
    op.drop_index("chat_messages_analysis_seq_idx",
                  table_name="chat_messages", schema="ai")
    op.drop_table("chat_messages", schema="ai")
