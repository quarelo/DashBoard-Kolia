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
def list_meetings(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    include_versions: bool = Query(False, description="Inclui versões superadas."),
    # Dashboard filters — operate on source_metadata JSONB.
    uf: str | None = Query(None, description="Filtra por UF (estado), ex: SP, RJ."),
    segmento: str | None = Query(None, description="Filtra por NOME_SEGMENTO (contém, case-insensitive)."),
    unidade: str | None = Query(None, description="Filtra por NOME_UNIDADE (contém, case-insensitive)."),
    formato: str | None = Query(None, description="Filtra por FORMATO_MEETING, ex: Vídeo, Presencial."),
    cnae: str | None = Query(None, description="Filtra por CNAE (exato)."),
    dt_meeting_from: str | None = Query(None, description="Data da reunião a partir de (YYYY-MM-DD)."),
    dt_meeting_to: str | None = Query(None, description="Data da reunião até (YYYY-MM-DD)."),
    user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    filters = [ImportedMeeting.owner_id == user.id]
    if not include_versions:
        filters.append(latest_version_only())
    # JSONB exact-match filters.
    if uf:
        filters.append(ImportedMeeting.source_metadata["UF"].astext == uf.upper())
    if cnae:
        filters.append(ImportedMeeting.source_metadata["CNAE"].astext == cnae)
    if formato:
        filters.append(func.lower(ImportedMeeting.source_metadata["FORMATO_MEETING"].astext) == formato.lower())
    # JSONB substring filters (case-insensitive).
    if segmento:
        filters.append(func.lower(ImportedMeeting.source_metadata["NOME_SEGMENTO"].astext).contains(segmento.lower()))
    if unidade:
        filters.append(func.lower(ImportedMeeting.source_metadata["NOME_UNIDADE"].astext).contains(unidade.lower()))
    # Date range on DT_MEETING (stored as string in source_metadata).
    if dt_meeting_from:
        filters.append(ImportedMeeting.source_metadata["DT_MEETING"].astext >= dt_meeting_from)
    if dt_meeting_to:
        filters.append(ImportedMeeting.source_metadata["DT_MEETING"].astext <= dt_meeting_to)
    total = db.scalar(select(func.count()).select_from(ImportedMeeting).where(*filters))
    items = db.scalars(select(ImportedMeeting).where(*filters)
                       .order_by(ImportedMeeting.created_at, ImportedMeeting.id).offset(offset).limit(limit))
    return {"total": total, "items": [meeting_detail(m) for m in items], "offset": offset, "limit": limit}


@router.get("/meetings/filters")
def available_filters(user: UserModel = Depends(get_current_user), db: Session = Depends(get_db)):
    """Distinct values for each dashboard filter, for populating dropdowns."""
    base = [ImportedMeeting.owner_id == user.id, latest_version_only()]

    def distinct_values(json_key: str) -> list[str]:
        col = ImportedMeeting.source_metadata[json_key].astext
        rows = db.execute(
            select(col).where(*base, col.isnot(None), col != "")
            .distinct().order_by(col)
        ).scalars().all()
        return list(rows)

    return {
        "uf": distinct_values("UF"),
        "segmento": distinct_values("NOME_SEGMENTO"),
        "unidade": distinct_values("NOME_UNIDADE"),
        "formato": distinct_values("FORMATO_MEETING"),
        "cnae": distinct_values("CNAE"),
    }


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
