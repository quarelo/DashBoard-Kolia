# Plano de Desenvolvimento — IA FastAPI `/analisar`

Este documento descreve o plano para desenvolver a parte de IA do projeto KOLIA usando **Python + FastAPI**, com endpoint `/analisar`, integração com **Postgres + pgvector**, divisão de transcrições em chunks e estrutura preparada para depois plugar Ollama ou LocalAI.

---

## 1. Objetivo

Criar um serviço de IA independente do backend Java.

O backend Java será responsável por:

- usuários
- login
- permissões
- regras principais do sistema
- receber ou gerenciar reuniões no sistema principal
- chamar a IA quando precisar processar uma transcrição

O serviço de IA em FastAPI será responsável por:

- receber a transcrição
- contar tokens
- dividir a reunião em chunks
- limpar/sanitizar cada chunk
- gerar resumo por chunk
- gerar embeddings
- salvar chunks no Postgres/pgvector
- consolidar um resumo final
- expor endpoints para buscar análise e chunks

---

## 2. Arquitetura

```txt
Frontend
   ↓
Backend Java Spring Boot
   ↓
IA Service FastAPI
   ↓
Postgres + pgvector
   ↓
Ollama ou LocalAI
```

A IA não depende do Java para ser desenvolvida agora.  
Basta definir um contrato de API que o Java vai chamar depois.

---

## 3. Contrato entre Java e IA

O backend Java futuramente vai chamar:

```txt
POST /analisar
```

Com o seguinte body:

```json
{
  "meeting_id": "11111111-1111-1111-1111-111111111111",
  "user_id": "22222222-2222-2222-2222-222222222222",
  "title": "Reunião com cliente X",
  "transcription": "texto completo da transcrição..."
}
```

Resposta esperada:

```json
{
  "analysis_id": "uuid-da-analise",
  "meeting_id": "11111111-1111-1111-1111-111111111111",
  "status": "DONE",
  "total_tokens": 44135,
  "total_chunks": 10,
  "final_summary": {}
}
```

---

## 4. Estrutura da pasta `IA/`

```txt
IA/
├── Dockerfile
├── .dockerignore
├── .env.example
├── requirements.txt
├── README.md
└── app/
    ├── __init__.py
    ├── main.py
    ├── core/
    │   ├── __init__.py
    │   ├── config.py
    │   └── database.py
    ├── models/
    │   ├── __init__.py
    │   └── analysis.py
    ├── schemas/
    │   ├── __init__.py
    │   └── analysis.py
    └── services/
        ├── __init__.py
        ├── token_service.py
        ├── chunk_service.py
        ├── llm_service.py
        └── analysis_service.py
```

---

## 5. Dependências

Arquivo:

```txt
IA/requirements.txt
```

```txt
fastapi==0.115.6
uvicorn[standard]==0.34.0
sqlalchemy==2.0.36
psycopg2-binary==2.9.10
pgvector==0.3.6
pydantic-settings==2.7.1
python-dotenv==1.0.1
```

### Explicação das dependências

```txt
fastapi              → API HTTP
uvicorn              → servidor ASGI
sqlalchemy           → ORM/conexão com banco
psycopg2-binary      → driver Postgres
pgvector             → suporte a coluna vector no SQLAlchemy
pydantic-settings    → leitura de env/config
python-dotenv        → suporte a .env local
```

---

## 6. Dockerfile da IA

Arquivo:

```txt
IA/Dockerfile
```

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 3000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3000"]
```

---

## 7. `.dockerignore`

Arquivo:

```txt
IA/.dockerignore
```

```dockerignore
__pycache__
*.pyc
.env
.venv
venv
logs/*
.git
.gitignore
Dockerfile
.dockerignore
```

---

## 8. `.env.example`

Arquivo:

```txt
IA/.env.example
```

```env
DATABASE_URL=postgresql+psycopg2://kolia:kolia@postgres:5432/kolia

MAX_TOKENS_PER_CHUNK=2500
OVERLAP_TOKENS=200

EMBEDDING_DIM=768

OLLAMA_GENERATE_URL=http://ollama:11434/api/generate
OLLAMA_EMBED_URL=http://ollama:11434/api/embed

MODEL=qwen2.5:3b
EMBEDDING_MODEL=nomic-embed-text
```

---

## 9. Configuração

Arquivo:

```txt
IA/app/core/config.py
```

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://kolia:kolia@postgres:5432/kolia"

    max_tokens_per_chunk: int = 2500
    overlap_tokens: int = 200

    embedding_dim: int = 768

    ollama_generate_url: str = "http://ollama:11434/api/generate"
    ollama_embed_url: str = "http://ollama:11434/api/embed"

    model: str = "qwen2.5:3b"
    embedding_model: str = "nomic-embed-text"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
```

---

## 10. Banco de dados

A IA vai criar e usar um schema separado chamado:

```txt
ai
```

Isso evita misturar tabelas do backend Java com tabelas da IA.

### Tabelas da IA

```txt
ai.meeting_analyses
ai.meeting_chunks
```

### `meeting_analyses`

Guarda a análise geral da reunião.

Campos principais:

```txt
id
external_meeting_id
external_user_id
title
status
total_tokens
total_chunks
final_summary
error_message
created_at
updated_at
```

### `meeting_chunks`

Guarda os pedaços da reunião.

Campos principais:

```txt
id
analysis_id
external_meeting_id
external_user_id
chunk_index
token_count
content
clean_content
chunk_summary
embedding
created_at
```

---

## 11. Conexão com banco

Arquivo:

```txt
IA/app/core/database.py
```

```python
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


def init_database():
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS ai"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
```

### Observação

Para MVP/dev, `Base.metadata.create_all()` é suficiente.

Depois, quando o projeto amadurecer, o ideal é trocar por:

```txt
Alembic migrations
```

---

## 12. Models SQLAlchemy

Arquivo:

```txt
IA/app/models/analysis.py
```

```python
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.core.database import Base


class MeetingAnalysis(Base):
    __tablename__ = "meeting_analyses"
    __table_args__ = {"schema": "ai"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    external_meeting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        index=True,
    )

    external_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="PENDING", index=True)

    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_chunks: Mapped[int] = mapped_column(Integer, default=0)

    final_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )

    chunks: Mapped[list["MeetingChunk"]] = relationship(
        back_populates="analysis",
        cascade="all, delete-orphan",
    )


class MeetingChunk(Base):
    __tablename__ = "meeting_chunks"
    __table_args__ = {"schema": "ai"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ai.meeting_analyses.id", ondelete="CASCADE"),
        index=True,
    )

    external_meeting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        index=True,
    )

    external_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    chunk_index: Mapped[int] = mapped_column(Integer)
    token_count: Mapped[int] = mapped_column(Integer, default=0)

    content: Mapped[str] = mapped_column(Text)
    clean_content: Mapped[str | None] = mapped_column(Text, nullable=True)

    chunk_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    embedding = mapped_column(
        Vector(settings.embedding_dim),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )

    analysis: Mapped[MeetingAnalysis] = relationship(
        back_populates="chunks",
    )
```

---

## 13. Registrar models

Arquivo:

```txt
IA/app/models/__init__.py
```

```python
from app.models.analysis import MeetingAnalysis, MeetingChunk
```

---

## 14. Schemas Pydantic

Arquivo:

```txt
IA/app/schemas/analysis.py
```

```python
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
```

---

## 15. Token service

Arquivo:

```txt
IA/app/services/token_service.py
```

```python
import re


_TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def count_tokens(text: str) -> int:
    # Estimativa simples para MVP.
    # Depois, trocar pelo tokenizer do modelo usado.
    if not text:
        return 0

    return len(_TOKEN_PATTERN.findall(text))


def split_text_by_tokens(
    text: str,
    max_tokens: int,
    overlap_tokens: int,
) -> list[str]:
    tokens = _TOKEN_PATTERN.findall(text)

    if not tokens:
        return []

    if len(tokens) <= max_tokens:
        return [text.strip()]

    chunks: list[str] = []
    start = 0

    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        chunk = " ".join(tokens[start:end]).strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(tokens):
            break

        start = max(0, end - overlap_tokens)

    return chunks
```

---

## 16. Chunk service

Arquivo:

```txt
IA/app/services/chunk_service.py
```

```python
import re


SMALL_TALK_PATTERNS = [
    r"\bbom dia\b",
    r"\bboa tarde\b",
    r"\bboa noite\b",
    r"\btudo bem\b",
    r"\bme ouvem\b",
    r"\best[aã]o me ouvindo\b",
    r"\bconseguem me ouvir\b",
    r"\bconseguem ver minha tela\b",
    r"\best[aã]o vendo minha tela\b",
    r"\bobrigado\b",
    r"\bvaleu\b",
    r"\bbeleza\b",
    r"\bshow\b",
    r"\btranquilo\b",
]


def sanitize_transcription(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def clean_chunk_text(text: str) -> str:
    cleaned = sanitize_transcription(text)

    for pattern in SMALL_TALK_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()
```

---

## 17. LLM service mockado

Arquivo:

```txt
IA/app/services/llm_service.py
```

```python
import hashlib
import math

from app.core.config import settings


def generate_mock_chunk_summary(clean_content: str) -> dict:
    # Mock inicial para validar fluxo, banco e endpoint.
    # Depois substituir por chamada real ao Ollama/LocalAI.
    preview = clean_content[:500]

    return {
        "temas_discutidos": [preview] if preview else [],
        "problemas_identificados": [],
        "decisoes_tomadas": [],
        "duvidas_em_aberto": [],
        "oportunidades_insights": [],
        "evidencias_importantes": [],
        "metricas_negocio": {
            "valor_venda": "",
            "valor_contrato": "",
            "quantidade_usuarios": "",
            "quantidade_licencas": "",
            "prazo": "",
            "desconto": "",
            "produtos_servicos_citados": [],
            "valores_financeiros_citados": [],
        },
    }


def consolidate_mock_summaries(chunk_summaries: list[dict]) -> dict:
    temas = []

    for summary in chunk_summaries:
        temas.extend(summary.get("temas_discutidos", []))

    return {
        "resumo_geral": "Resumo mockado gerado para validar o fluxo inicial da IA.",
        "temas_agrupados": [
            {
                "tema": "Conteúdo principal da reunião",
                "pontos": temas[:10],
            }
        ],
        "problemas_identificados": [],
        "decisoes_tomadas": [],
        "duvidas_em_aberto": [],
        "oportunidades_insights": [],
        "evidencias_importantes": [],
        "metricas_negocio": {
            "valor_venda": "",
            "valor_contrato": "",
            "quantidade_usuarios": "",
            "quantidade_licencas": "",
            "prazo": "",
            "desconto": "",
            "produtos_servicos_citados": [],
            "valores_financeiros_citados": [],
        },
        "acoes_recomendadas": [],
    }


def generate_fake_embedding(text: str) -> list[float]:
    # Embedding fake determinístico apenas para testar pgvector.
    # Depois substituir por Ollama /api/embed ou LocalAI /v1/embeddings.
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values = []

    for i in range(settings.embedding_dim):
        byte = digest[i % len(digest)]
        value = (byte / 255.0) - 0.5
        values.append(value)

    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]
```

---

## 18. Analysis service

Arquivo:

```txt
IA/app/services/analysis_service.py
```

```python
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.analysis import MeetingAnalysis, MeetingChunk
from app.schemas.analysis import AnalyzeRequest
from app.services.chunk_service import clean_chunk_text, sanitize_transcription
from app.services.llm_service import (
    consolidate_mock_summaries,
    generate_fake_embedding,
    generate_mock_chunk_summary,
)
from app.services.token_service import count_tokens, split_text_by_tokens


def analyze_meeting(db: Session, payload: AnalyzeRequest) -> MeetingAnalysis:
    analysis = MeetingAnalysis(
        external_meeting_id=payload.meeting_id,
        external_user_id=payload.user_id,
        title=payload.title,
        status="PROCESSING",
    )

    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    try:
        transcription = sanitize_transcription(payload.transcription)
        total_tokens = count_tokens(transcription)

        chunks = split_text_by_tokens(
            transcription,
            max_tokens=settings.max_tokens_per_chunk,
            overlap_tokens=settings.overlap_tokens,
        )

        chunk_summaries = []

        for index, chunk_content in enumerate(chunks, start=1):
            clean_content = clean_chunk_text(chunk_content)
            token_count = count_tokens(chunk_content)
            summary = generate_mock_chunk_summary(clean_content)
            embedding = generate_fake_embedding(clean_content)

            chunk = MeetingChunk(
                analysis_id=analysis.id,
                external_meeting_id=payload.meeting_id,
                external_user_id=payload.user_id,
                chunk_index=index,
                token_count=token_count,
                content=chunk_content,
                clean_content=clean_content,
                chunk_summary=summary,
                embedding=embedding,
            )

            db.add(chunk)
            chunk_summaries.append(summary)

        final_summary = consolidate_mock_summaries(chunk_summaries)

        analysis.total_tokens = total_tokens
        analysis.total_chunks = len(chunks)
        analysis.final_summary = final_summary
        analysis.status = "DONE"

        db.commit()
        db.refresh(analysis)

        return analysis

    except Exception as error:
        analysis.status = "FAILED"
        analysis.error_message = str(error)

        db.commit()
        db.refresh(analysis)

        return analysis
```

---

## 19. FastAPI main

Arquivo:

```txt
IA/app/main.py
```

```python
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db, init_database
from app.models.analysis import MeetingAnalysis, MeetingChunk
from app.schemas.analysis import (
    AnalysisDetailResponse,
    AnalyzeRequest,
    AnalyzeResponse,
    ChunkResponse,
)
from app.services.analysis_service import analyze_meeting

app = FastAPI(
    title="KOLIA IA Service",
    version="0.1.0",
)


@app.on_event("startup")
def startup():
    init_database()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "kolia-ia-service",
    }


@app.post("/analisar", response_model=AnalyzeResponse)
def analisar(payload: AnalyzeRequest, db: Session = Depends(get_db)):
    analysis = analyze_meeting(db, payload)

    return AnalyzeResponse(
        analysis_id=analysis.id,
        meeting_id=analysis.external_meeting_id,
        status=analysis.status,
        total_tokens=analysis.total_tokens,
        total_chunks=analysis.total_chunks,
        final_summary=analysis.final_summary,
    )


@app.get("/analises/{analysis_id}", response_model=AnalysisDetailResponse)
def get_analysis(analysis_id: UUID, db: Session = Depends(get_db)):
    analysis = db.get(MeetingAnalysis, analysis_id)

    if not analysis:
        raise HTTPException(status_code=404, detail="Análise não encontrada.")

    return AnalysisDetailResponse(
        analysis_id=analysis.id,
        meeting_id=analysis.external_meeting_id,
        user_id=analysis.external_user_id,
        title=analysis.title,
        status=analysis.status,
        total_tokens=analysis.total_tokens,
        total_chunks=analysis.total_chunks,
        final_summary=analysis.final_summary,
        error_message=analysis.error_message,
    )


@app.get("/analises/by-meeting/{meeting_id}", response_model=AnalysisDetailResponse)
def get_analysis_by_meeting(meeting_id: UUID, db: Session = Depends(get_db)):
    stmt = (
        select(MeetingAnalysis)
        .where(MeetingAnalysis.external_meeting_id == meeting_id)
        .order_by(MeetingAnalysis.created_at.desc())
        .limit(1)
    )

    analysis = db.execute(stmt).scalar_one_or_none()

    if not analysis:
        raise HTTPException(
            status_code=404,
            detail="Análise não encontrada para esta reunião.",
        )

    return AnalysisDetailResponse(
        analysis_id=analysis.id,
        meeting_id=analysis.external_meeting_id,
        user_id=analysis.external_user_id,
        title=analysis.title,
        status=analysis.status,
        total_tokens=analysis.total_tokens,
        total_chunks=analysis.total_chunks,
        final_summary=analysis.final_summary,
        error_message=analysis.error_message,
    )


@app.get("/analises/{analysis_id}/chunks", response_model=list[ChunkResponse])
def list_chunks(analysis_id: UUID, db: Session = Depends(get_db)):
    analysis = db.get(MeetingAnalysis, analysis_id)

    if not analysis:
        raise HTTPException(status_code=404, detail="Análise não encontrada.")

    stmt = (
        select(MeetingChunk)
        .where(MeetingChunk.analysis_id == analysis_id)
        .order_by(MeetingChunk.chunk_index.asc())
    )

    chunks = db.execute(stmt).scalars().all()

    return [
        ChunkResponse(
            id=chunk.id,
            chunk_index=chunk.chunk_index,
            token_count=chunk.token_count,
            content=chunk.content,
            clean_content=chunk.clean_content,
            chunk_summary=chunk.chunk_summary,
        )
        for chunk in chunks
    ]
```

---

## 20. Serviço no Docker Compose

No `infra/docker-compose.yml`, o serviço da IA deve ficar parecido com:

```yaml
ia-service:
  container_name: kolia-ia-service
  build:
    context: ../IA
    dockerfile: Dockerfile
  ports:
    - "3000:3000"
  environment:
    DATABASE_URL: postgresql+psycopg2://kolia:kolia@postgres:5432/kolia
    MAX_TOKENS_PER_CHUNK: 2500
    OVERLAP_TOKENS: 200
    EMBEDDING_DIM: 768
    OLLAMA_GENERATE_URL: http://ollama:11434/api/generate
    OLLAMA_EMBED_URL: http://ollama:11434/api/embed
    MODEL: ${OLLAMA_MODEL:-qwen2.5:3b}
    EMBEDDING_MODEL: ${EMBEDDING_MODEL:-nomic-embed-text}
  depends_on:
    - postgres
    - ollama
  networks:
    - kolia-network
  restart: unless-stopped
```

---

## 21. Como testar

### Subir IA

Dentro da pasta `infra`:

```bash
docker compose up -d --build ia-service
```

### Ver logs da IA

```bash
docker compose logs -f ia-service
```

### Testar health

```bash
curl http://localhost:3000/health
```

Resposta esperada:

```json
{
  "status": "ok",
  "service": "kolia-ia-service"
}
```

### Testar `/analisar`

```bash
curl -X POST http://localhost:3000/analisar \
  -H "Content-Type: application/json" \
  -d '{
    "meeting_id": "11111111-1111-1111-1111-111111111111",
    "user_id": "22222222-2222-2222-2222-222222222222",
    "title": "Reunião teste",
    "transcription": "Bom dia, tudo bem? Cliente comentou dificuldade na integração com ERP. Foi decidido marcar uma reunião técnica na sexta-feira."
  }'
```

Resposta esperada:

```json
{
  "analysis_id": "uuid",
  "meeting_id": "11111111-1111-1111-1111-111111111111",
  "status": "DONE",
  "total_tokens": 30,
  "total_chunks": 1,
  "final_summary": {
    "resumo_geral": "Resumo mockado gerado para validar o fluxo inicial da IA."
  }
}
```

---

## 22. Ver dados no Postgres

Entrar no banco:

```bash
cd infra
docker compose exec postgres psql -U kolia -d kolia
```

Listar schemas:

```sql
\dn
```

Ver análises:

```sql
SELECT
  id,
  external_meeting_id,
  title,
  status,
  total_tokens,
  total_chunks,
  created_at
FROM ai.meeting_analyses;
```

Ver chunks:

```sql
SELECT
  id,
  analysis_id,
  chunk_index,
  token_count,
  LEFT(clean_content, 120) AS preview
FROM ai.meeting_chunks
ORDER BY chunk_index;
```

---

## 23. Próximo passo: trocar mock por IA real

Depois que o banco e endpoint estiverem funcionando, trocar no arquivo:

```txt
app/services/llm_service.py
```

As funções:

```python
generate_mock_chunk_summary()
consolidate_mock_summaries()
generate_fake_embedding()
```

Por chamadas reais.

---

## 24. Chamada real para Ollama — resumo

Futuramente, criar algo assim:

```python
import json
import httpx

from app.core.config import settings


def generate_chunk_summary_with_ollama(clean_content: str) -> dict:
    prompt = (
        "Você é um especialista em análise de reuniões corporativas.\n\n"
        "Analise o trecho abaixo e retorne JSON válido com:\n"
        "- temas_discutidos\n"
        "- problemas_identificados\n"
        "- decisoes_tomadas\n"
        "- duvidas_em_aberto\n"
        "- oportunidades_insights\n"
        "- evidencias_importantes\n"
        "- metricas_negocio\n\n"
        f"TRECHO:\n{clean_content}"
    )

    response = httpx.post(
        settings.ollama_generate_url,
        json={
            "model": settings.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0,
                "num_predict": 2048,
            },
        },
        timeout=180,
    )

    response.raise_for_status()
    data = response.json()

    return json.loads(data["response"])
```

---

## 25. Chamada real para Ollama — embedding

Futuramente, criar algo assim:

```python
import httpx

from app.core.config import settings


def generate_embedding_with_ollama(text: str) -> list[float]:
    response = httpx.post(
        settings.ollama_embed_url,
        json={
            "model": settings.embedding_model,
            "input": text,
        },
        timeout=120,
    )

    response.raise_for_status()
    data = response.json()

    return data["embeddings"][0]
```

---

## 26. Decisão importante: dimensão do embedding

Antes de usar embedding real, confirmar a dimensão do modelo escolhido.

Exemplos comuns:

```txt
384
768
1024
```

O campo no banco precisa bater:

```python
embedding = mapped_column(Vector(settings.embedding_dim), nullable=True)
```

Se o embedding tiver 768 dimensões:

```env
EMBEDDING_DIM=768
```

Se tiver 384:

```env
EMBEDDING_DIM=384
```

Se mudar a dimensão depois da tabela criada, será necessário recriar a tabela ou fazer migration.

---

## 27. Evolução depois do MVP

Depois do `/analisar` básico:

1. adicionar Alembic
2. adicionar resumo real com Ollama/LocalAI
3. adicionar embedding real
4. adicionar endpoint `/analises/{analysis_id}/ask`
5. buscar chunks semelhantes com pgvector
6. usar os chunks como contexto para responder perguntas
7. adicionar status assíncrono se a análise demorar muito
8. criar logs de processamento por análise
9. criar retry por chunk
10. criar endpoint para reprocessar uma reunião

---

## 28. Checklist MVP

```txt
[ ] Criar estrutura da pasta IA
[ ] Criar requirements.txt
[ ] Criar Dockerfile
[ ] Criar .dockerignore
[ ] Criar config.py
[ ] Criar database.py
[ ] Criar models
[ ] Criar schemas
[ ] Criar token_service.py
[ ] Criar chunk_service.py
[ ] Criar llm_service.py mockado
[ ] Criar analysis_service.py
[ ] Criar main.py
[ ] Subir container da IA
[ ] Testar /health
[ ] Testar /analisar
[ ] Ver dados em ai.meeting_analyses
[ ] Ver dados em ai.meeting_chunks
[ ] Confirmar chunking
[ ] Confirmar embedding fake salvo
[ ] Depois trocar mock por IA real
```

---

## 29. Resumo final

Neste primeiro momento, o objetivo não é acertar a IA perfeita.

O objetivo é validar o fluxo:

```txt
receber transcrição
→ criar análise
→ dividir em chunks
→ limpar chunks
→ gerar resumo mockado
→ gerar embedding fake
→ salvar no pgvector
→ retornar resposta
```

Depois que esse fluxo estiver funcionando, a troca para IA real fica muito mais simples.
