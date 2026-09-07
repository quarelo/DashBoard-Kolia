"""Endpoints que servem as análises reais das transcrições para o dashboard.

Substituem os dados mockados do frontend. A leitura vem de ``ai.meeting_analyses``
(ver ``services/analysis_read.py``); o chat é um proxy para o RAG da IA
(``POST /analises/{id}/chat``, contrato em
``docs/superpowers/specs/2026-08-26-meeting-rag-chat-api-design.md``).
"""
from uuid import UUID

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from core.auth import get_current_user
from core.database import get_db
from models.user import UserModel
from services import analysis_read
from services.ia_gateway import get_ia_client, readiness

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# Limites do contrato do chat da IA (ChatRequest).
_MAX_HISTORY = 6
_MAX_TURN_CHARS = 1000


@router.get("/overview")
def dashboard_overview(_user: UserModel = Depends(get_current_user), db: Session = Depends(get_db)):
    return analysis_read.overview(db)


@router.get("/meetings")
def dashboard_meetings(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    _user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return analysis_read.list_analyses(db, offset, limit)


@router.get("/meetings/{analysis_id}")
def dashboard_meeting_detail(
    analysis_id: UUID,
    _user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = analysis_read.get_analysis(db, analysis_id)
    if item is None:
        raise HTTPException(404, "Análise não encontrada.")
    item.update(readiness({"status": item["status"], "summary_is_final": item["summary_is_final"]}))
    return item


def _clean_history(raw) -> list[dict]:
    """Normaliza o histórico para o formato que a IA aceita: papéis alternados,
    começando em 'user' e terminando em 'assistant', no máximo 6 mensagens."""
    turns = []
    for entry in raw if isinstance(raw, list) else []:
        role = (entry or {}).get("role")
        content = str((entry or {}).get("content", "")).strip()
        if role in ("user", "assistant") and content:
            turns.append({"role": role, "content": content[:_MAX_TURN_CHARS]})
    # colapsa papéis repetidos mantendo o último de cada sequência
    collapsed: list[dict] = []
    for turn in turns:
        if collapsed and collapsed[-1]["role"] == turn["role"]:
            collapsed[-1] = turn
        else:
            collapsed.append(turn)
    while collapsed and collapsed[0]["role"] != "user":
        collapsed.pop(0)
    while collapsed and collapsed[-1]["role"] != "assistant":
        collapsed.pop()
    return collapsed[-_MAX_HISTORY:]


@router.post("/meetings/{analysis_id}/chat")
def dashboard_meeting_chat(
    analysis_id: UUID,
    payload: dict = Body(...),
    _user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
    client: httpx.Client = Depends(get_ia_client),
):
    item = analysis_read.get_analysis(db, analysis_id)
    if item is None:
        raise HTTPException(404, "Análise não encontrada.")
    if item["status"] != "DONE":
        raise HTTPException(409, {
            "code": "RAG_NOT_READY",
            "message": "A indexação desta reunião ainda não terminou. Tente novamente em instantes.",
        })

    question = str(payload.get("question", "")).strip()
    if not 2 <= len(question) <= 500:
        raise HTTPException(422, "A pergunta deve ter entre 2 e 500 caracteres.")

    body = {"question": question, "history": _clean_history(payload.get("history"))}
    top_k = payload.get("top_k")
    if isinstance(top_k, int) and 1 <= top_k <= 6:
        body["top_k"] = top_k

    try:
        # A geração do chat pode demorar (carga de modelo + inferência no host);
        # o timeout padrão do cliente da IA, de 30s, não cobre isso.
        response = client.post(
            f"/analises/{analysis_id}/chat", json=body,
            timeout=httpx.Timeout(180.0, connect=5.0),
        )
    except httpx.HTTPError as error:
        raise HTTPException(503, {"code": "IA_UNAVAILABLE", "message": "Serviço de IA indisponível."}) from error

    if response.status_code == 404:
        raise HTTPException(404, "Análise não encontrada na IA.")
    if response.status_code == 409:
        raise HTTPException(409, {"code": "RAG_NOT_READY", "message": "Índice da reunião indisponível para chat."})
    if response.status_code in (401, 403):
        raise HTTPException(502, {"code": "IA_AUTH_FAILED", "message": "A IA recusou a autenticação do backend."})
    if response.status_code == 422:
        raise HTTPException(422, "Pergunta ou histórico inválidos para o chat.")
    if response.status_code >= 500:
        raise HTTPException(503, {"code": "IA_UNAVAILABLE", "message": "A IA não respondeu. Tente novamente."})

    return response.json()
