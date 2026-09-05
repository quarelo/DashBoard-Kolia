from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# One .env for the whole repo, at the root, next to docker-compose.yml.
# Inside a container this path does not exist and Compose supplies the same
# values as real environment variables, which outrank any file regardless.
ROOT_ENV = Path(__file__).resolve().parents[4] / ".env"


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://kolia:kolia@postgres:5432/kolia"
    max_tokens_per_chunk: int = 2000
    overlap_tokens: int = 120
    embedding_dim: int = 768
    ollama_generate_url: str = "http://ollama:11434/api/generate"
    ollama_embed_url: str = "http://ollama:11434/api/embed"
    ollama_think: bool = True
    ollama_num_predict: int = 512
    ollama_chunk_think: bool = False
    ollama_chunk_num_predict: int = 192
    ollama_consolidation_think: bool = False
    ollama_consolidation_num_predict: int = 384
    ollama_keep_alive: str = "30m"
    ollama_generate_timeout_seconds: float = 600.0
    ollama_embedding_timeout_seconds: float = 120.0
    ollama_read_timeout_retries: int = 1
    ollama_json_repair_enabled: bool = True
    chat_num_predict: int = 512
    chat_temperature: float = 0.0
    chat_context_length: int = 8192
    chat_similarity_threshold: float = 0.55
    chat_max_evidence_chars: int = 2000
    chat_generate_timeout_seconds: float = 120.0
    analysis_worker_concurrency: int = 1
    # Two concurrent chunk requests nearly halved the measured Ollama path on
    # the reference transcription; keep it configurable for smaller hosts.
    chunk_processing_concurrency: int = 2
    partial_chunk_count: int = 6
    max_llm_chunks: int = 15
    fast_transcription_retention_ratio: float = 0.05
    fast_deterministic_consolidation: bool = True
    model: str = Field(default="qwen2.5:3b", validation_alias=AliasChoices("MODEL", "OLLAMA_MODEL"))
    chunk_model: str = Field(default="gemma3:1b", validation_alias=AliasChoices("CHUNK_MODEL", "OLLAMA_CHUNK_MODEL"))
    consolidation_model: str = Field(default="gemma3:1b", validation_alias=AliasChoices("CONSOLIDATION_MODEL", "OLLAMA_CONSOLIDATION_MODEL"))
    embedding_model: str = "nomic-embed-text"
    # Seeds for the ETA fit before this host has finished any analysis.
    # Anchored on measured 1-chunk runs (~32s) and 48-chunk runs (~16s/chunk).
    eta_default_overhead_seconds: float = 16.0
    eta_default_seconds_per_chunk: float = 16.0

    model_config = SettingsConfigDict(
        env_file=ROOT_ENV, env_file_encoding="utf-8", extra="ignore",
        protected_namespaces=(),
    )


settings = Settings()
