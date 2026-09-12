"""Excluir uma reunião: a análise no `ai` e a importação no `core`, numa transação.

É a exceção à fronteira dos schemas registrada no CLAUDE.md ("Serviços"): o
backend apaga direto as linhas do `ai`. Pela IA seriam duas transações em dois
serviços, e uma falha entre elas deixaria a reunião meio apagada.
"""
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from models.meeting import ImportedMeeting
from models.user import UserModel
from schemas.user import RoleEnum

# Tudo que o `ai` guarda de uma análise, filhos antes do pai, na ordem das FKs.
# Tabela nova no `ai` ligada à análise precisa entrar aqui: senão sobra lixo, ou
# a FK barra a exclusão inteira (analysis_submissions já é ON DELETE RESTRICT).
# tests/test_delete_meeting.py confere esta lista contra o schema do banco.
AI_ROWS_BY_ANALYSIS = (
    ("ai.chat_messages", "analysis_id"),
    ("ai.chunk_passages", "analysis_id"),
    ("ai.meeting_chunks", "analysis_id"),
    ("ai.analysis_submissions", "analysis_id"),
    ("ai.meeting_analyses", "id"),
)

# Os status em que o worker da IA ainda escreve na análise: os mesmos
# `_RECOVERABLE_STATUSES` de ia/src/app/services/analysis_worker.py. Apagar por
# baixo dele falharia o próximo commit do worker no meio do caminho.
IN_PROGRESS_STATUSES = frozenset({"PROCESSING", "ANALYZING", "DASHBOARD_READY", "EMBEDDING"})


def delete_meeting(db: Session, user: UserModel, analysis_id: UUID) -> None:
    """Delete the analysis and every `core.meetings` row pointing at it, or nothing.

    The caller commits nothing itself: this commits once at the end, and any
    exception before that leaves the transaction for the caller to roll back.

    Dashboard reads are not scoped by owner, but deleting is irreversible and
    disappears for everyone: a regular user deletes only what they imported, a
    sales director deletes anything.
    """
    meetings = db.scalars(
        select(ImportedMeeting).where(ImportedMeeting.analysis_id == analysis_id).with_for_update()
    ).all()
    if user.role != RoleEnum.SALES_DIRECTOR and not any(m.owner_id == user.id for m in meetings):
        raise HTTPException(403, {
            "code": "DELETE_FORBIDDEN",
            "message": "Só quem importou a reunião ou um diretor comercial pode excluí-la.",
        })

    # Locked so the status cannot move to an in-progress state between this check
    # and the delete.
    analysis = db.execute(
        text("SELECT status FROM ai.meeting_analyses WHERE id = :id FOR UPDATE"),
        {"id": str(analysis_id)},
    ).first()
    if analysis is None and not meetings:
        raise HTTPException(404, "Análise não encontrada.")
    if analysis is not None and analysis.status in IN_PROGRESS_STATUSES:
        raise HTTPException(409, {
            "code": "ANALYSIS_IN_PROGRESS",
            "message": "A análise ainda está em processamento. Exclua depois que ela terminar.",
        })

    for table, column in AI_ROWS_BY_ANALYSIS:
        db.execute(text(f"DELETE FROM {table} WHERE {column} = :id"), {"id": str(analysis_id)})
    for meeting in meetings:
        db.delete(meeting)
    db.commit()
