from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.app.core.config import settings
from src.app.core.database import SessionLocal, get_db, init_database
from src.app.models.analysis import MeetingAnalysis, MeetingChunk
from src.app.schemas.analysis import (
    AnalysisDetailResponse, AnalyzeRequest, AnalyzeResponse, ChunkResponse,
    SemanticSearchRequest, SemanticSearchResponse,
    CategoryEvidenceResponse,
    ChatRequest, ChatResponse,
)
from src.app.services.analysis_service import build_analysis_progress, prepare_analysis
from src.app.services.analysis_worker import AnalysisWorker
from src.app.services.analysis_submission import SubmissionConflict, submit_idempotent
from src.app.services.eta_service import estimate_analysis, estimate_backlog, estimate_batch
from src.app.services.chat_service import answer_analysis_question
from src.app.services.rag_service import (
    RagNotReadyError,
    search_analysis_categories,
    search_analysis_chunks,
)

analysis_worker = AnalysisWorker(
    SessionLocal,
    concurrency=settings.analysis_worker_concurrency,
)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_database()
    analysis_worker.start()
    analysis_worker.recover()
    try:
        yield
    finally:
        analysis_worker.stop()


app = FastAPI(title="KOLIA IA Service", version="0.1.0", lifespan=lifespan)


@app.get("/")
def root():
    return {"message": "Kolia IA FastAPI"}


@app.get("/health")
def health():
    return {"status": "ok", "service": "kolia-ia-service"}


@app.post("/analisar", response_model=AnalyzeResponse, status_code=202)
def analisar(
    payload: AnalyzeRequest,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(
        default=None, min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$",
    ),
):
    if idempotency_key is None:
        analysis = prepare_analysis(db, payload)
        analysis_worker.submit(analysis.id)
    else:
        try:
            analysis = submit_idempotent(
                db, payload, idempotency_key, prepare_analysis, analysis_worker.submit,
            )
        except SubmissionConflict as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
    chunks = _chunks_for_analysis(db, analysis.id) if idempotency_key is not None else []
    progress = build_analysis_progress(analysis, chunks)
    return AnalyzeResponse(analysis_id=analysis.id, meeting_id=analysis.external_meeting_id, status=analysis.status, total_tokens=analysis.total_tokens, final_summary=analysis.final_summary, error_message=analysis.error_message, **progress)


def _detail(
    analysis: MeetingAnalysis, chunks: list[MeetingChunk]
) -> AnalysisDetailResponse:
    progress = build_analysis_progress(analysis, chunks)
    return AnalysisDetailResponse(analysis_id=analysis.id, meeting_id=analysis.external_meeting_id, user_id=analysis.external_user_id, title=analysis.title, status=analysis.status, total_tokens=analysis.total_tokens, final_summary=analysis.final_summary, error_message=analysis.error_message, **progress)


def _chunks_for_analysis(db: Session, analysis_id: UUID) -> list[MeetingChunk]:
    statement = select(MeetingChunk).where(
        MeetingChunk.analysis_id == analysis_id
    ).order_by(MeetingChunk.chunk_index.asc())
    return list(db.execute(statement).scalars().all())


@app.get("/analises/{analysis_id}", response_model=AnalysisDetailResponse)
def get_analysis(analysis_id: UUID, db: Session = Depends(get_db)):
    analysis = db.get(MeetingAnalysis, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Análise não encontrada.")
    return _detail(analysis, _chunks_for_analysis(db, analysis.id))


@app.get("/analises/by-meeting/{meeting_id}", response_model=AnalysisDetailResponse)
def get_analysis_by_meeting(meeting_id: UUID, db: Session = Depends(get_db)):
    statement = select(MeetingAnalysis).where(MeetingAnalysis.external_meeting_id == meeting_id).order_by(MeetingAnalysis.created_at.desc()).limit(1)
    analysis = db.execute(statement).scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Análise não encontrada para esta reunião.")
    return _detail(analysis, _chunks_for_analysis(db, analysis.id))


@app.get("/fila")
def queue_estimate(db: Session = Depends(get_db)):
    """Everything still unfinished, and roughly how long the backlog needs."""
    return estimate_backlog(db)


@app.get("/estimativa")
def batch_estimate(analyses: int = Query(ge=1, le=100_000),
                   chunks_each: int = Query(default=1, ge=1, le=1_000),
                   db: Session = Depends(get_db)):
    """Cost of a batch that has not been submitted yet, e.g. a whole CSV import."""
    return estimate_batch(db, analyses=analyses, chunks_each=chunks_each)


@app.get("/analises/{analysis_id}/estimativa")
def analysis_estimate(analysis_id: UUID, db: Session = Depends(get_db)):
    analysis = db.get(MeetingAnalysis, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Análise não encontrada.")
    return {"analysis_id": analysis.id, "status": analysis.status,
            "total_chunks": analysis.total_chunks, **estimate_analysis(db, analysis)}


@app.get("/analises/{analysis_id}/chunks", response_model=list[ChunkResponse])
def list_chunks(analysis_id: UUID, db: Session = Depends(get_db)):
    if not db.get(MeetingAnalysis, analysis_id):
        raise HTTPException(status_code=404, detail="Análise não encontrada.")
    statement = select(MeetingChunk).where(MeetingChunk.analysis_id == analysis_id).order_by(MeetingChunk.chunk_index.asc())
    chunks = db.execute(statement).scalars().all()
    return [ChunkResponse(id=chunk.id, chunk_index=chunk.chunk_index, token_count=chunk.token_count, content=chunk.content, clean_content=chunk.clean_content, chunk_summary=chunk.chunk_summary) for chunk in chunks]


@app.post(
    "/analises/{analysis_id}/buscar",
    response_model=SemanticSearchResponse,
)
def semantic_search(
    analysis_id: UUID,
    payload: SemanticSearchRequest,
    db: Session = Depends(get_db),
):
    try:
        return search_analysis_chunks(
            db, analysis_id, payload.query, payload.top_k
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RagNotReadyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get(
    "/analises/{analysis_id}/evidencias",
    response_model=CategoryEvidenceResponse,
)
def category_evidence(
    analysis_id: UUID,
    top_k: int = 4,
    db: Session = Depends(get_db),
):
    try:
        return search_analysis_categories(db, analysis_id, top_k)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RagNotReadyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post(
    "/analises/{analysis_id}/chat",
    response_model=ChatResponse,
)
def chat_with_analysis(
    analysis_id: UUID,
    payload: ChatRequest,
    db: Session = Depends(get_db),
):
    try:
        return answer_analysis_question(db, analysis_id, payload)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RagNotReadyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail="Chat temporariamente indisponível.",
        ) from error
