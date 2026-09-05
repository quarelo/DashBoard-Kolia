import hashlib
import re
from uuid import UUID

import httpx
from fastapi import HTTPException

from core.config import settings


def get_ia_client():
    with httpx.Client(base_url=settings.ia_service_url, timeout=httpx.Timeout(30, connect=5)) as client:
        yield client


def readiness(payload: dict) -> dict:
    status = payload.get("status")
    return {
        "summary_ready": bool(payload.get("summary_is_final")) or status in {
            "DASHBOARD_READY", "EMBEDDING", "DONE", "DASHBOARD_READY_WITH_EMBEDDING_ERROR",
        },
        "rag_ready": status == "DONE",
    }


def request_ia(client: httpx.Client, method: str, path: str, **kwargs) -> dict:
    try:
        response = client.request(method, path, **kwargs)
        if response.status_code == 409:
            raise HTTPException(409, {"code": "ANALYSIS_NOT_READY", "message": "Análise em andamento ou indisponível para repetição."})
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError("Unexpected IA response")
        return result
    except (httpx.HTTPError, ValueError) as error:
        raise HTTPException(503, {"code": "IA_UNAVAILABLE", "message": "Serviço de IA indisponível. Tente novamente com a mesma reunião."}) from error


def start_analysis(client: httpx.Client, meeting) -> dict:
    # Include the persistent internal ID: equal text in different meetings is not shared RAG context.
    key = hashlib.sha256(f"meeting-analysis-v1:{meeting.id}:{meeting.transcription_hash}".encode()).hexdigest()
    transcription = re.sub(r"\blocutor_(\d+)\b\s*:?\s*", r"[LOCUTOR \1]: ", meeting.transcription, flags=re.I)
    result = request_ia(client, "POST", "/analisar", headers={"Idempotency-Key": key}, json={
        "meeting_id": str(meeting.id), "title": meeting.title, "transcription": transcription,
    })
    try:
        UUID(result["analysis_id"])
        if UUID(result["meeting_id"]) != meeting.id:
            raise ValueError("Wrong meeting")
    except (KeyError, ValueError, TypeError, AttributeError) as error:
        raise HTTPException(503, {"code": "INVALID_IA_RESPONSE", "message": "Resposta inválida do serviço de IA."}) from error
    return {**result, **readiness(result)}


def get_analysis(client: httpx.Client, analysis_id: UUID) -> dict:
    result = request_ia(client, "GET", f"/analises/{analysis_id}")
    return {**result, **readiness(result)}
