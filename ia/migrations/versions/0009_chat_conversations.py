"""chat_conversations: várias conversas por reunião

Até aqui havia uma conversa por análise: `chat_messages` era chaveada só por
`analysis_id`, e o botão "Nova conversa" do frontend apenas limpava a tela — a
pergunta seguinte continuava a mesma conversa guardada, e reabrir a reunião
trazia tudo de volta misturado. Cada mensagem passa a pertencer a uma conversa, e
a reunião pode ter quantas quiser.

As mensagens que já existiam viram uma conversa por análise, com a primeira
pergunta como título, antes de `conversation_id` virar NOT NULL.

Revision ID: 0009
Revises: 0008
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_conversations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("analysis_id", UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        # A lista mostra a conversa mexida por último primeiro, como no claude.ai.
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["analysis_id"], ["ai.meeting_analyses.id"],
                                ondelete="CASCADE"),
        schema="ai",
    )
    op.create_index(
        "chat_conversations_analysis_updated_idx", "chat_conversations",
        ["analysis_id", "updated_at"], schema="ai",
    )

    op.add_column(
        "chat_messages",
        sa.Column("conversation_id", UUID(as_uuid=True), nullable=True),
        schema="ai",
    )
    op.execute("""
        INSERT INTO ai.chat_conversations (id, analysis_id, title, created_at, updated_at)
        SELECT gen_random_uuid(), m.analysis_id,
               left(coalesce((SELECT first.content FROM ai.chat_messages first
                              WHERE first.analysis_id = m.analysis_id AND first.role = 'user'
                              ORDER BY first.seq LIMIT 1), 'Conversa'), 80),
               min(m.created_at), max(m.created_at)
        FROM ai.chat_messages m
        GROUP BY m.analysis_id
    """)
    op.execute("""
        UPDATE ai.chat_messages m SET conversation_id = c.id
        FROM ai.chat_conversations c
        WHERE c.analysis_id = m.analysis_id
    """)
    op.alter_column("chat_messages", "conversation_id", nullable=False, schema="ai")
    op.create_foreign_key(
        "chat_messages_conversation_id_fkey", "chat_messages", "chat_conversations",
        ["conversation_id"], ["id"], source_schema="ai", referent_schema="ai",
        ondelete="CASCADE",
    )
    op.create_index(
        "chat_messages_conversation_seq_idx", "chat_messages",
        ["conversation_id", "seq"], schema="ai",
    )


def downgrade() -> None:
    # Volta a uma conversa por análise: as mensagens ficam, as conversas se fundem.
    op.drop_index("chat_messages_conversation_seq_idx",
                  table_name="chat_messages", schema="ai")
    op.drop_constraint("chat_messages_conversation_id_fkey", "chat_messages",
                       schema="ai", type_="foreignkey")
    op.drop_column("chat_messages", "conversation_id", schema="ai")
    op.drop_index("chat_conversations_analysis_updated_idx",
                  table_name="chat_conversations", schema="ai")
    op.drop_table("chat_conversations", schema="ai")
