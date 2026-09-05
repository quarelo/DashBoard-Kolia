from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class MeetingImport(Base):
    __tablename__ = "meeting_imports"
    __table_args__ = (
        UniqueConstraint("owner_id", "file_hash"),
        UniqueConstraint("owner_id", "content_hash"),
        {"schema": "core"},
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[int] = mapped_column(ForeignKey("core.users.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    file_hash: Mapped[str] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(64))
    imported_count: Mapped[int] = mapped_column(Integer)
    skipped_count: Mapped[int] = mapped_column(Integer)
    versioned_count: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ImportedMeeting(Base):
    __tablename__ = "meetings"
    # A changed transcription for a known external_id lands as a new version rather
    # than overwriting: older versions keep their own analysis, chunks and citations.
    __table_args__ = (UniqueConstraint("owner_id", "external_id", "version"), {"schema": "core"})

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[int] = mapped_column(ForeignKey("core.users.id"), index=True)
    import_id: Mapped[UUID] = mapped_column(ForeignKey("core.meeting_imports.id"), index=True)
    external_id: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    title: Mapped[str] = mapped_column(Text)
    transcription: Mapped[str] = mapped_column(Text)
    transcription_hash: Mapped[str] = mapped_column(String(64))
    source_metadata: Mapped[dict] = mapped_column(JSONB)
    analysis_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
