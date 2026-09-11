from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# One .env for the whole repo, at the root, next to docker-compose.yml.
# Inside a container this path does not exist and Compose supplies the same
# values as real environment variables, which outrank any file regardless.
ROOT_ENV = Path(__file__).resolve().parents[4] / ".env"


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://kolia:kolia@postgres:5432/kolia"
    # The IA verifies tokens the backend issued, so both must read the same key.
    # The single root .env spells it JWT_SECRET, which is also the name Compose
    # interpolates; accepting either keeps this service starting from that file.
    # min_length because PyJWT raises InvalidKeyError per request on an empty key,
    # which surfaces as a 500 on every authenticated call instead of a boot error.
    secret_key: str = Field(
        min_length=32,
        validation_alias=AliasChoices("SECRET_KEY", "JWT_SECRET"),
    )
    algorithm: str = "HS256"
    max_tokens_per_chunk: int = 2000
    overlap_tokens: int = 120
    embedding_dim: int = 768
    # Retrieval granularity, independent of the chunk size used for summarising.
    # ~400 tokens is a few sentences: small enough that one price does not get
    # averaged away, large enough to carry its own context.
    passage_tokens: int = 400
    passage_overlap_tokens: int = 40
    ollama_generate_url: str = "http://ollama:11434/api/generate"
    ollama_embed_url: str = "http://ollama:11434/api/embed"
    ollama_think: bool = True
    ollama_num_predict: int = 512
    ollama_chunk_think: bool = False
    # 192 was cheaper per call but truncated often, and a truncated JSON costs a
    # full retry at double the budget: measured over 10 real meetings, 192 spent
    # 140s with 3 retries against 97s and none at 256. Asking for more up front
    # is the cheaper trade here. 384 since qwen3.5:4b-q4_K_M took over the chunk:
    # it truncated at none of 256/384/512, and an unused budget costs nothing.
    ollama_chunk_num_predict: int = 384
    # Ceiling for the per-chunk budget. Above 512 the extra tokens bought nothing
    # on real chunks (768 measured slower than 512 with the same retry count).
    ollama_chunk_num_predict_max: int = 512
    # On, and not only for the codes: measured over 14 real meetings, dropping the
    # catalogue was 2.3x SLOWER (301s against 132s, 8 truncations against none).
    # The block seems to anchor the answer — without it the model rambles in
    # pontos_chave and overruns the budget, and each overrun costs a full retry.
    chunk_motive_classification: bool = True
    # Whether the codes the model declares outrank the rules. Off for a 1B that
    # enumerated the catalogue instead of choosing (all five churn codes on a CRM
    # demo: churn 100 against 30 from the rules). On for qwen3.5:4b-q4_K_M, with
    # analysis_service dropping a declaration that covers all five codes.
    trust_declared_motives: bool = True
    ollama_consolidation_think: bool = False
    ollama_consolidation_num_predict: int = 768
    ollama_keep_alive: str = "30m"
    ollama_generate_timeout_seconds: float = 600.0
    ollama_embedding_timeout_seconds: float = 120.0
    ollama_read_timeout_retries: int = 1
    ollama_json_repair_enabled: bool = True
    chat_num_predict: int = 512
    # Not 0: greedy decoding is what produced the one-word answers. Measured over
    # five questions on an indexed meeting, 0.4 turned "Preço orçamentos" into "O
    # cliente falou sobre preço." and "Produtos" into "Produtos: Estoque, BIP
    # (Código de barra)", with the two questions that already answered well coming
    # back word for word the same. The alternative tried in the same run — a
    # worked example in the re-read prompt — made it refuse two of the five, with
    # or without temperature.
    chat_temperature: float = 0.4
    chat_context_length: int = 32768
    chat_similarity_threshold: float = 0.55
    chat_max_evidence_chars: int = 2000
    # What the reader sees as proof, not what the model reads. The two were the
    # same 2000 characters, which put a wall of transcript under a one-line answer;
    # shrinking what the model reads is not an option, since three 700-character
    # passages measured worse than one of 2000. The citation is re-cut around the
    # answer's own words instead, and only for display.
    chat_citation_chars: int = 350
    chat_generate_timeout_seconds: float = 120.0
    analysis_worker_concurrency: int = 1
    # Two concurrent chunk requests nearly halved the measured Ollama path on
    # the reference transcription; keep it configurable for smaller hosts.
    chunk_processing_concurrency: int = 2
    partial_chunk_count: int = 6
    max_llm_chunks: int = 15
    fast_transcription_retention_ratio: float = 0.05
    # Off: the deterministic path wrote raw transcript into final_summary (budget
    # with "[L67]:" speaker tags inside), which the chat then served as the answer.
    fast_deterministic_consolidation: bool = False
    # One extra Ollama call per analysis (never per chunk): see
    # docs/product-catalog-grounding.md for why the granularity trade-off was
    # accepted for this host. Off falls back to whatever `produto` the
    # consolidation step already produced, ungrounded.
    product_grounding_enabled: bool = True
    product_grounding_top_k: int = 5
    # Distance decides the clear-cut cases so the model is only asked to
    # arbitrate real ambiguity: at or below `confident`, the closest catalogue
    # match is accepted with no Ollama call; above `plausible`, a candidate is
    # dropped before ever reaching the model. Chosen to sit around the same
    # cosine-distance ballpark as chat_similarity_threshold=0.55 (equivalent to
    # distance 0.45) already in use for the RAG chat's own relevance cutoff;
    # not yet calibrated against this catalogue's real embeddings the way that
    # one was, since that needs the model actually running on real meetings.
    product_grounding_confident_distance: float = 0.20
    product_grounding_plausible_distance: float = 0.45
    model: str = Field(default="qwen3.5:4b-q4_K_M", validation_alias=AliasChoices("MODEL", "OLLAMA_MODEL"))
    chunk_model: str = Field(default="qwen3.5:4b-q4_K_M", validation_alias=AliasChoices("CHUNK_MODEL", "OLLAMA_CHUNK_MODEL"))
    consolidation_model: str = Field(default="qwen3.5:4b-q4_K_M", validation_alias=AliasChoices("CONSOLIDATION_MODEL", "OLLAMA_CONSOLIDATION_MODEL"))
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
