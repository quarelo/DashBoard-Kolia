from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class AnalyzeRequest(BaseModel):
    meeting_id: UUID
    user_id: UUID | None = None
    title: str = Field(min_length=1)
    transcription: str = Field(min_length=1)
    metadata: dict[str, str] | None = Field(
        default=None,
        description="Business context from the CSV (TP_RECURSO, NOME_SEGMENTO, etc.) "
                    "injected into analysis prompts for richer insights.",
    )


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


class CategoryEvidenceResponse(BaseModel):
    analysis_id: UUID
    ready: bool
    categories: dict[str, list[SemanticSearchResult]]


class ChatHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1000)

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("A mensagem não pode estar vazia.")
        return stripped


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    history: list[ChatHistoryMessage] = Field(default_factory=list, max_length=6)
    top_k: int = Field(default=4, ge=1, le=6)

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 2:
            raise ValueError("A pergunta deve ter pelo menos dois caracteres.")
        return stripped

    @model_validator(mode="after")
    def validate_history_order(self):
        if not self.history:
            return self
        if self.history[0].role != "user":
            raise ValueError("O histórico deve começar com uma mensagem do usuário.")
        for previous, current in zip(self.history, self.history[1:]):
            if previous.role == current.role:
                raise ValueError("As mensagens do histórico devem alternar os papéis.")
        if self.history[-1].role != "assistant":
            raise ValueError("O histórico deve terminar com uma resposta do assistente.")
        return self


class ChatCitation(BaseModel):
    chunk_id: UUID
    chunk_index: int
    excerpt: str
    similarity: float


class ChatMessageOut(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    grounded: bool | None = None
    fallback_reason: str | None = None
    created_at: datetime


class ChatHistoryResponse(BaseModel):
    analysis_id: UUID
    messages: list[ChatMessageOut]


class ChatResponse(BaseModel):
    analysis_id: UUID
    answer: str
    citations: list[ChatCitation]
    grounded: bool
    fallback_reason: Literal[
        "insufficient_evidence", "model_unavailable", "unsupported_answer",
        "unsafe_request",
    ] | None = None
