import hashlib
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
import jwt
from fastapi import HTTPException

from core.config import settings


# The IA verifies every analysis route with the shared secret, so the backend has
# to authenticate as a service rather than forward whoever is logged in: the worker
# and retry paths run without a request context, and a user token would expire
# mid-batch. Minutes, not days, because this token never leaves the internal call.
SERVICE_TOKEN_MINUTES = 10


def service_token() -> str:
    return jwt.encode(
        {"sub": "kolia-backend", "role": "SERVICE",
         "exp": datetime.now(timezone.utc) + timedelta(minutes=SERVICE_TOKEN_MINUTES)},
        settings.secret_key, algorithm=settings.algorithm,
    )


def get_ia_client():
    with httpx.Client(
        base_url=settings.ia_service_url,
        timeout=httpx.Timeout(30, connect=5),
        headers={"Authorization": f"Bearer {service_token()}"},
    ) as client:
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
        # A rejected token is a configuration fault, not an outage, and calling it
        # "indisponível" sends whoever is on call to restart a healthy service.
        # Both sides must sign with the same secret; retrying will not fix it.
        if response.status_code in (401, 403):
            raise HTTPException(502, {
                "code": "IA_AUTH_FAILED",
                "message": "A IA recusou a autenticação do backend. Verifique se os "
                           "dois serviços leem o mesmo JWT_SECRET.",
            })
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
