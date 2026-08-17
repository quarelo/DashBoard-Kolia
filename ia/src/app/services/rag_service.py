from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.app.models.analysis import MeetingAnalysis, MeetingChunk
from src.app.services.llm_service import generate_embedding


class RagNotReadyError(RuntimeError):
    pass


def search_analysis_chunks(
    db: Session,
    analysis_id: UUID,
    query: str,
    top_k: int = 5,
) -> dict:
    analysis = db.get(MeetingAnalysis, analysis_id)
    if analysis is None:
        raise ValueError("Análise não encontrada.")

    missing = db.execute(
        select(func.count(MeetingChunk.id)).where(
            MeetingChunk.analysis_id == analysis_id,
            MeetingChunk.embedding.is_(None),
        )
    ).scalar_one()
    if analysis.status != "DONE" or missing:
        raise RagNotReadyError(
            "A busca semântica estará disponível quando todos os embeddings terminarem."
        )

    query_embedding = generate_embedding(query)
    distance = MeetingChunk.embedding.cosine_distance(query_embedding)
    statement = (
        select(MeetingChunk, distance.label("distance"))
        .where(
            MeetingChunk.analysis_id == analysis_id,
            MeetingChunk.embedding.is_not(None),
        )
        .order_by(distance.asc())
        .limit(top_k)
    )
    results = []
    for chunk, cosine_distance in db.execute(statement).all():
        similarity = max(0.0, min(1.0, 1.0 - float(cosine_distance)))
        content = chunk.clean_content or chunk.content
        results.append({
            "chunk_id": chunk.id,
            "chunk_index": chunk.chunk_index,
            "excerpt": content[:700],
            "similarity": round(similarity, 4),
        })
    return {
        "analysis_id": analysis_id,
        "query": query,
        "ready": True,
        "results": results,
    }
