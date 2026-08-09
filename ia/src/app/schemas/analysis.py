from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    meeting_id: UUID
    user_id: UUID | None = None
    title: str = Field(min_length=1)
    transcription: str = Field(min_length=1)


class AnalyzeResponse(BaseModel):
    analysis_id: UUID
    meeting_id: UUID
    status: str
    total_tokens: int
    total_chunks: int
    final_summary: dict[str, Any] | None = None


class ChunkResponse(BaseModel):
    id: UUID
    chunk_index: int
    token_count: int
    content: str
    clean_content: str | None = None
    chunk_summary: dict[str, Any] | None = None


class AnalysisDetailResponse(BaseModel):
    analysis_id: UUID
    meeting_id: UUID
    user_id: UUID | None = None
    title: str
    status: str
    total_tokens: int
    total_chunks: int
    final_summary: dict[str, Any] | None = None
    error_message: str | None = None
