from collections import defaultdict
from pathlib import PurePath

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from models.meeting import ImportedMeeting, MeetingImport
from models.user import UserModel
from services.meeting_parser import ImportValidationError, ParsedImport


def _existing_state(db: Session, owner_id: int, external_ids: list[str]):
    """Latest version per external_id, plus every transcription hash ever stored for it.

    The hash set is what stops an A → B → A edit cycle from growing a new version
    on every upload: content already stored under that id is skipped, not re-versioned.
    """
    latest: dict[str, ImportedMeeting] = {}
    seen_hashes: dict[str, set[str]] = defaultdict(set)
    rows = db.scalars(select(ImportedMeeting).where(
        ImportedMeeting.owner_id == owner_id,
        ImportedMeeting.external_id.in_(external_ids),
    ))
    for row in rows:
        seen_hashes[row.external_id].add(row.transcription_hash)
        if row.external_id not in latest or row.version > latest[row.external_id].version:
            latest[row.external_id] = row
    return latest, seen_hashes


def import_meetings(db: Session, owner_id: int, filename: str, parsed: ParsedImport) -> MeetingImport:
    """Commit the whole validated import atomically. Never dispatch IA here."""
    try:
        # Serialize imports by owner across processes; constraints provide a second guard.
        owner = db.scalar(select(UserModel).where(UserModel.id == owner_id).with_for_update())
        if owner is None:
            raise ImportValidationError("Usuário não encontrado.", "INVALID_OWNER", 401)
        duplicate = db.scalar(select(MeetingImport.id).where(
            MeetingImport.owner_id == owner_id,
            or_(MeetingImport.file_hash == parsed.file_hash,
                MeetingImport.content_hash == parsed.content_hash),
        ))
        if duplicate:
            raise ImportValidationError("Este arquivo já foi importado.", "DUPLICATE_IMPORT", 409)

        latest, seen_hashes = _existing_state(
            db, owner_id, [m.external_id for m in parsed.meetings])
        created, revised = [], []
        for item in parsed.meetings:
            if item.transcription_hash in seen_hashes[item.external_id]:
                continue  # Same content already stored under this id, in some version.
            (revised if item.external_id in latest else created).append(item)
        if not created and not revised:
            raise ImportValidationError("Todas as reuniões já foram importadas.", "DUPLICATE_IMPORT", 409)

        batch = MeetingImport(
            owner_id=owner_id, filename=PurePath(filename.replace("\\", "/")).name[:255],
            file_hash=parsed.file_hash, content_hash=parsed.content_hash,
            imported_count=len(created), versioned_count=len(revised),
            skipped_count=len(parsed.meetings) - len(created) - len(revised),
        )
        db.add(batch)
        db.flush()
        for item in created + revised:
            previous = latest.get(item.external_id)
            db.add(ImportedMeeting(
                owner_id=owner_id, import_id=batch.id, external_id=item.external_id,
                version=previous.version + 1 if previous else 1,
                title=item.title, transcription=item.transcription,
                transcription_hash=item.transcription_hash, source_metadata=item.metadata,
                # analysis_id stays NULL: a new version is analysed on its own,
                # so the previous version keeps its analysis, chunks and citations.
            ))
        db.commit()
        db.refresh(batch)
        return batch
    except Exception:
        db.rollback()
        raise
