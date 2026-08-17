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
    processed_chunks: int = 0
    progress_percent: float = 0.0
    is_partial: bool = True
    estimated_seconds_remaining: int | None = None
    summary_stage: str = "PRELIMINARY"
    summary_is_final: bool = False
    summary_progress_percent: float = 0.0
    embedding_progress_percent: float = 0.0
    summary_estimated_seconds_remaining: int | None = None
    final_summary: dict[str, Any] | None = None
    error_message: str | None = None


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
    processed_chunks: int = 0
    progress_percent: float = 0.0
    is_partial: bool = True
    estimated_seconds_remaining: int | None = None
    summary_stage: str = "PRELIMINARY"
    summary_is_final: bool = False
    summary_progress_percent: float = 0.0
    embedding_progress_percent: float = 0.0
    summary_estimated_seconds_remaining: int | None = None
    final_summary: dict[str, Any] | None = None
    error_message: str | None = None


class SemanticSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    top_k: int = Field(default=5, ge=1, le=10)


class SemanticSearchResult(BaseModel):
    chunk_id: UUID
    chunk_index: int
    excerpt: str
    similarity: float


class SemanticSearchResponse(BaseModel):
    analysis_id: UUID
    query: str
    ready: bool
    results: list[SemanticSearchResult]
