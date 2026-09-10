import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Computed, DateTime, ForeignKey,
    Identity, Index, Integer, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.core.config import settings
from src.app.core.database import Base


class MeetingAnalysis(Base):
    __tablename__ = "meeting_analyses"
    __table_args__ = {"schema": "ai"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_meeting_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    external_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="PENDING", index=True)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_chunks: Mapped[int] = mapped_column(Integer, default=0)
    final_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    summary_attempt_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    summary_attempt_started_chunks: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    summary_stage: Mapped[str] = mapped_column(
        Text, default="PRELIMINARY", server_default="PRELIMINARY"
    )
    summary_is_final: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    source_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    chunks: Mapped[list["MeetingChunk"]] = relationship(back_populates="analysis", cascade="all, delete-orphan")


class MeetingChunk(Base):
    __tablename__ = "meeting_chunks"
    __table_args__ = {"schema": "ai"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ai.meeting_analyses.id", ondelete="CASCADE"), index=True)
    external_meeting_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    external_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text)
    clean_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    embedding = mapped_column(Vector(settings.embedding_dim), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    analysis: Mapped[MeetingAnalysis] = relationship(back_populates="chunks")
    passages: Mapped[list["ChunkPassage"]] = relationship(
        back_populates="chunk", cascade="all, delete-orphan")


class ChunkPassage(Base):
    """A slice of a chunk, embedded on its own.

    A chunk is sized for summarising — around 2000 tokens, which keeps the number
    of LLM calls down. That size is wrong for retrieval: one vector averaged over
    two thousand words dissolves the sentence that names a price, and asking the
    chat about values returned five chunks above the similarity threshold, none of
    them the four that mention R$. Passages give the search something small enough
    to point at, while the chunk stays whole for the summary.
    """

    __tablename__ = "chunk_passages"
    # Two runners can both find a chunk unindexed (the worker recovers on startup);
    # the constraint stops the second from doubling the index.
    __table_args__ = (
        UniqueConstraint("chunk_id", "passage_index",
                         name="chunk_passages_chunk_passage_key"),
        Index("ix_ai_chunk_passages_search", "search_vector",
              postgresql_using="gin"),
        {"schema": "ai"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai.meeting_chunks.id", ondelete="CASCADE"), index=True)
    # Denormalised so retrieval can filter by analysis without joining every time;
    # search is always scoped to one analysis.
    analysis_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    passage_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    embedding = mapped_column(Vector(settings.embedding_dim), nullable=True)
    # Generated by Postgres from `content`, so lexical search never drifts out of
    # sync with the text it indexes.
    search_vector = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('portuguese', content)", persisted=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    chunk: Mapped[MeetingChunk] = relationship(back_populates="passages")


class ChatMessage(Base):
    """Um turno da conversa sobre uma reunião.

    Uma conversa por análise: o usuário escolhe a reunião e continua de onde
    parou. Antes disto o histórico vivia só no payload que o navegador reenviava,
    então recarregar a página apagava tudo.
    """

    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint("role in ('user', 'assistant')",
                        name="chat_messages_role_check"),
        Index("chat_messages_analysis_seq_idx", "analysis_id", "seq"),
        {"schema": "ai"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Ordem da conversa: `created_at` empata dentro de um mesmo commit, porque o
    # `now()` do Postgres é o tempo da transação.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=False))
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai.meeting_analyses.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    # O veredito do servidor guardado junto da mensagem: sem ele, reabrir a
    # conversa não distingue uma recusa de uma resposta.
    grounded: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    fallback_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
