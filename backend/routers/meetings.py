from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import aliased
from sqlalchemy.orm import Session

from core.auth import get_current_user
from core.database import get_db
from models.meeting import ImportedMeeting, MeetingImport
from models.user import UserModel
from services.ia_gateway import get_analysis, get_ia_client, start_analysis
from services.meeting_import_service import import_meetings
from services.meeting_parser import ImportValidationError, parse_meeting_file

router = APIRouter(prefix="/api", tags=["meetings"])
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def import_detail(batch):
    return {"import_id": batch.id, "filename": batch.filename,
            "status": "IMPORTED", "imported_count": batch.imported_count,
            "versioned_count": batch.versioned_count,
            "skipped_count": batch.skipped_count, "created_at": batch.created_at}


def meeting_detail(meeting, include_transcription=False):
    result = {"id": meeting.id, "external_id": meeting.external_id,
              "version": meeting.version, "title": meeting.title,
              "metadata": meeting.source_metadata,
              "analysis_id": meeting.analysis_id, "created_at": meeting.created_at}
    if include_transcription:
        result["transcription"] = meeting.transcription
    return result


def owned_meeting(db, owner_id, meeting_id, lock=False):
    statement = select(ImportedMeeting).where(
        ImportedMeeting.id == meeting_id, ImportedMeeting.owner_id == owner_id,
    )
    if lock:
        statement = statement.with_for_update()
    meeting = db.scalar(statement)
    if meeting is None:
        raise HTTPException(404, "Reunião não encontrada.")
    return meeting


@router.post("/imports", status_code=201)
def upload_meetings(file: UploadFile = File(...), user: UserModel = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        content = file.file.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Limite de upload: 5 MiB.")
        parsed = parse_meeting_file(content, file.filename or "")
        return import_detail(import_meetings(db, user.id, file.filename or "", parsed))
    except ImportValidationError as error:
        raise HTTPException(error.status_code, {"code": error.code, "message": str(error)}) from error
    finally:
        file.file.close()


@router.get("/imports/{import_id}")
def get_import(import_id: UUID, user: UserModel = Depends(get_current_user), db: Session = Depends(get_db)):
    batch = db.scalar(select(MeetingImport).where(MeetingImport.id == import_id, MeetingImport.owner_id == user.id))
    if batch is None:
        raise HTTPException(404, "Importação não encontrada.")
    return import_detail(batch)


def latest_version_only():
    """Restrict to rows no newer version supersedes, for the same owner and external_id."""
    newer = aliased(ImportedMeeting)
    return ~select(newer.id).where(
        newer.owner_id == ImportedMeeting.owner_id,
        newer.external_id == ImportedMeeting.external_id,
        newer.version > ImportedMeeting.version,
    ).exists()


@router.get("/meetings")
def list_meetings(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                  include_versions: bool = Query(False, description="Inclui versões superadas."),
                  user: UserModel = Depends(get_current_user), db: Session = Depends(get_db)):
    filters = [ImportedMeeting.owner_id == user.id]
    if not include_versions:
        filters.append(latest_version_only())
    total = db.scalar(select(func.count()).select_from(ImportedMeeting).where(*filters))
    items = db.scalars(select(ImportedMeeting).where(*filters)
                       .order_by(ImportedMeeting.created_at, ImportedMeeting.id).offset(offset).limit(limit))
    return {"total": total, "items": [meeting_detail(m) for m in items], "offset": offset, "limit": limit}


@router.get("/meetings/{meeting_id}/versions")
def meeting_versions(meeting_id: UUID, user: UserModel = Depends(get_current_user), db: Session = Depends(get_db)):
    """Full history for the external_id this meeting belongs to, oldest first."""
    meeting = owned_meeting(db, user.id, meeting_id)
    rows = db.scalars(select(ImportedMeeting).where(
        ImportedMeeting.owner_id == user.id,
        ImportedMeeting.external_id == meeting.external_id,
    ).order_by(ImportedMeeting.version))
    return {"external_id": meeting.external_id, "items": [meeting_detail(m) for m in rows]}


@router.get("/meetings/{meeting_id}")
def get_meeting(meeting_id: UUID, user: UserModel = Depends(get_current_user), db: Session = Depends(get_db)):
    return meeting_detail(owned_meeting(db, user.id, meeting_id), include_transcription=True)


@router.post("/meetings/{meeting_id}/analysis", status_code=202)
def analyze_meeting(meeting_id: UUID, user: UserModel = Depends(get_current_user), db: Session = Depends(get_db), client: httpx.Client = Depends(get_ia_client)):
    meeting = owned_meeting(db, user.id, meeting_id, lock=True)
    try:
        if meeting.analysis_id:
            return get_analysis(client, meeting.analysis_id)
        result = start_analysis(client, meeting)
        meeting.analysis_id = UUID(result["analysis_id"])
        db.commit()
        return result
    finally:
        # Release locks also on timeout; a retry uses the identical key in IA.
        db.rollback()


@router.get("/meetings/{meeting_id}/analysis")
def analysis_status(meeting_id: UUID, user: UserModel = Depends(get_current_user), db: Session = Depends(get_db), client: httpx.Client = Depends(get_ia_client)):
    meeting = owned_meeting(db, user.id, meeting_id)
    if meeting.analysis_id is None:
        raise HTTPException(404, "Esta reunião ainda não possui análise.")
    return get_analysis(client, meeting.analysis_id)
