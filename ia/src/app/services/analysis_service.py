from sqlalchemy.orm import Session

from src.app.core.config import settings
from src.app.models.analysis import MeetingAnalysis, MeetingChunk
from src.app.schemas.analysis import AnalyzeRequest
from src.app.services.chunk_service import clean_chunk_text, sanitize_transcription
from src.app.services.llm_service import consolidate_mock_summaries, generate_fake_embedding, generate_mock_chunk_summary
from src.app.services.token_service import count_tokens, split_text_by_tokens


def analyze_meeting(db: Session, payload: AnalyzeRequest) -> MeetingAnalysis:
    analysis = MeetingAnalysis(external_meeting_id=payload.meeting_id, external_user_id=payload.user_id, title=payload.title, status="PROCESSING")
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    try:
        transcription = sanitize_transcription(payload.transcription)
        chunks = split_text_by_tokens(transcription, settings.max_tokens_per_chunk, settings.overlap_tokens)
        summaries = []
        for index, content in enumerate(chunks, start=1):
            clean_content = clean_chunk_text(content)
            summary = generate_mock_chunk_summary(clean_content)
            db.add(MeetingChunk(analysis_id=analysis.id, external_meeting_id=payload.meeting_id, external_user_id=payload.user_id, chunk_index=index, token_count=count_tokens(content), content=content, clean_content=clean_content, chunk_summary=summary, embedding=generate_fake_embedding(clean_content)))
            summaries.append(summary)
        analysis.total_tokens = count_tokens(transcription)
        analysis.total_chunks = len(chunks)
        analysis.final_summary = consolidate_mock_summaries(summaries)
        analysis.status = "DONE"
        db.commit()
        db.refresh(analysis)
        return analysis
    except Exception as error:
        db.rollback()
        analysis = db.merge(analysis)
        analysis.status = "FAILED"
        analysis.error_message = str(error)
        db.commit()
        db.refresh(analysis)
        return analysis
