import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
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
