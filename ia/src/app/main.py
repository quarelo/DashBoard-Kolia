from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.app.core.config import settings
from src.app.core.database import SessionLocal, get_db, init_database
from src.app.models.analysis import MeetingAnalysis, MeetingChunk
from src.app.schemas.analysis import AnalysisDetailResponse, AnalyzeRequest, AnalyzeResponse, ChunkResponse
from src.app.services.analysis_service import prepare_analysis
from src.app.services.analysis_worker import AnalysisWorker

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
def analisar(payload: AnalyzeRequest, db: Session = Depends(get_db)):
    analysis = prepare_analysis(db, payload)
    analysis_worker.submit(analysis.id)
    return AnalyzeResponse(analysis_id=analysis.id, meeting_id=analysis.external_meeting_id, status=analysis.status, total_tokens=analysis.total_tokens, total_chunks=analysis.total_chunks, final_summary=analysis.final_summary, error_message=analysis.error_message)


def _detail(analysis: MeetingAnalysis) -> AnalysisDetailResponse:
    return AnalysisDetailResponse(analysis_id=analysis.id, meeting_id=analysis.external_meeting_id, user_id=analysis.external_user_id, title=analysis.title, status=analysis.status, total_tokens=analysis.total_tokens, total_chunks=analysis.total_chunks, final_summary=analysis.final_summary, error_message=analysis.error_message)


@app.get("/analises/{analysis_id}", response_model=AnalysisDetailResponse)
def get_analysis(analysis_id: UUID, db: Session = Depends(get_db)):
    analysis = db.get(MeetingAnalysis, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Análise não encontrada.")
    return _detail(analysis)


@app.get("/analises/by-meeting/{meeting_id}", response_model=AnalysisDetailResponse)
def get_analysis_by_meeting(meeting_id: UUID, db: Session = Depends(get_db)):
    statement = select(MeetingAnalysis).where(MeetingAnalysis.external_meeting_id == meeting_id).order_by(MeetingAnalysis.created_at.desc()).limit(1)
    analysis = db.execute(statement).scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Análise não encontrada para esta reunião.")
    return _detail(analysis)


@app.get("/analises/{analysis_id}/chunks", response_model=list[ChunkResponse])
def list_chunks(analysis_id: UUID, db: Session = Depends(get_db)):
    if not db.get(MeetingAnalysis, analysis_id):
        raise HTTPException(status_code=404, detail="Análise não encontrada.")
    statement = select(MeetingChunk).where(MeetingChunk.analysis_id == analysis_id).order_by(MeetingChunk.chunk_index.asc())
    chunks = db.execute(statement).scalars().all()
    return [ChunkResponse(id=chunk.id, chunk_index=chunk.chunk_index, token_count=chunk.token_count, content=chunk.content, clean_content=chunk.clean_content, chunk_summary=chunk.chunk_summary) for chunk in chunks]
