import hashlib
import json
import re
from collections.abc import Callable
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.app.models.analysis import MeetingAnalysis
from src.app.models.submission import AnalysisSubmission
from src.app.schemas.analysis import AnalyzeRequest


class SubmissionConflict(Exception):
    """A key was already claimed and cannot safely create another analysis."""


def submit_idempotent(
    db: Session,
    payload: AnalyzeRequest,
    key: str,
    prepare: Callable[..., MeetingAnalysis],
    submit: Callable[[UUID], None],
) -> MeetingAnalysis:
    """Persist ownership before preparation, and the result before enqueueing.

    Preparation saves the mapping through on_created in the same transaction as
    the analysis and its chunks. A crash after that commit can replay the result.
    Failures before creation leave the key claimed for review; never expire or
    automatically reclaim it. The existing worker recovers mapped analyses on
    startup, so repeated HTTP requests do not enqueue additional processing.
    """
    if re.fullmatch(r"[0-9a-f]{64}", key) is None:
        raise ValueError("Idempotency-Key deve ser um SHA-256 hexadecimal minúsculo.")

    canonical_payload = json.dumps(
        payload.model_dump(mode="json"), sort_keys=True,
        separators=(",", ":"), ensure_ascii=False,
    )
    payload_hash = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
    claim = AnalysisSubmission(key=key, payload_hash=payload_hash)
    db.add(claim)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.get(AnalysisSubmission, key)
        if existing is None:
            raise
        if existing.payload_hash != payload_hash:
            raise SubmissionConflict(
                "Idempotency-Key já utilizada com outro conteúdo."
            ) from None
        if existing.analysis_id is not None:
            analysis = db.get(MeetingAnalysis, existing.analysis_id)
            if analysis is not None:
                return analysis
        raise SubmissionConflict(
            "Solicitação já recebida; a criação está em andamento ou requer revisão."
        ) from None

    def link_created_analysis(analysis: MeetingAnalysis) -> None:
        claim.analysis_id = analysis.id

    analysis = prepare(db, payload, on_created=link_created_analysis)
    submit(analysis.id)
    return analysis
