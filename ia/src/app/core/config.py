from pydantic_settings import BaseSettings, SettingsConfigDict


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
    analysis_worker_concurrency: int = 1
    chunk_processing_concurrency: int = 1
    partial_chunk_count: int = 6
    max_llm_chunks: int = 15
    fast_transcription_retention_ratio: float = 0.05
    fast_deterministic_consolidation: bool = True
    model: str = "qwen2.5:3b"
    chunk_model: str = "gemma3:1b"
    consolidation_model: str = "gemma3:1b"
    embedding_model: str = "nomic-embed-text"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
