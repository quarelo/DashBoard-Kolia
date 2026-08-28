import argparse
from uuid import UUID

from sqlalchemy import select

from src.app.core.database import SessionLocal
from src.app.models.analysis import MeetingAnalysis, MeetingChunk
from src.app.services.analysis_service import (
    build_compact_final_summary,
    build_deterministic_chunk_summary,
    merge_deterministic_evidence,
)
from src.app.services.llm_service import complete_missing_fields


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("analysis_id", type=UUID)
    args = parser.parse_args()
    with SessionLocal() as db:
        analysis = db.get(MeetingAnalysis, args.analysis_id)
        if analysis is None:
            raise ValueError("análise não encontrada")
        chunks = list(db.execute(
            select(MeetingChunk)
            .where(MeetingChunk.analysis_id == analysis.id)
            .order_by(MeetingChunk.chunk_index)
        ).scalars().all())
        rebuilt = 0
        deterministic_keys = {"resumo_chunk", "temas_discutidos", "pontos_chave"}
        for chunk in chunks:
            if chunk.chunk_summary and set(chunk.chunk_summary) == deterministic_keys:
                chunk.chunk_summary = build_deterministic_chunk_summary(
                    chunk.clean_content or chunk.content
                )
                rebuilt += 1
            elif chunk.chunk_summary:
                chunk.chunk_summary = merge_deterministic_evidence(
                    chunk.chunk_summary,
                    chunk.clean_content or chunk.content,
                )
        summaries = [chunk.chunk_summary for chunk in chunks]
        analysis.final_summary = complete_missing_fields(
            build_compact_final_summary(summaries), summaries
        )
        db.commit()
        print({"analysis_id": str(analysis.id), "rebuilt_chunks": rebuilt})


if __name__ == "__main__":
    main()
