import re

SMALL_TALK_PATTERNS = [r"\bbom dia\b", r"\bboa tarde\b", r"\bboa noite\b", r"\btudo bem\b", r"\bme ouvem\b", r"\best[aã]o me ouvindo\b", r"\bconseguem me ouvir\b", r"\bconseguem ver minha tela\b", r"\best[aã]o vendo minha tela\b", r"\bobrigado\b", r"\bvaleu\b", r"\bbeleza\b", r"\bshow\b", r"\btranquilo\b"]


def sanitize_transcription(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\x00", " ")).strip()


def clean_chunk_text(text: str) -> str:
    cleaned = sanitize_transcription(text)
    for pattern in SMALL_TALK_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).strip()
