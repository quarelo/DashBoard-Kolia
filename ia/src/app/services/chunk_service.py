import re


_SPEAKER_PATTERN = re.compile(r"\[LOCUTOR\s+(\d+)\]\s*:\s*", re.IGNORECASE)
_COMPACT_SPEAKER_PATTERN = re.compile(r"\[L(\d+)\]\s*:\s*", re.IGNORECASE)
_SMALL_TALK_TURN = re.compile(
    r"^(?:(?:bom dia|boa tarde|boa noite|tudo bem|obrigad[oa]|valeu|beleza|"
    r"show|tranquilo|ok|sim|não)[\s,!.?]*)+$",
    re.IGNORECASE,
)


def sanitize_transcription(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\x00", " ")).strip()


def _is_small_talk_turn(text: str) -> bool:
    return bool(_SMALL_TALK_TURN.fullmatch(text.strip()))


def clean_transcription(text: str) -> str:
    sanitized = sanitize_transcription(text)
    matches = list(_SPEAKER_PATTERN.finditer(sanitized))
    if not matches:
        return sanitized

    turns: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(sanitized)
        speaker = match.group(1)
        content = sanitized[match.end():end].strip()
        if not content or _is_small_talk_turn(content):
            continue

        identity = (speaker, content.casefold())
        if identity in seen:
            continue
        seen.add(identity)

        if turns and turns[-1][0] == speaker:
            turns[-1] = (speaker, f"{turns[-1][1]} {content}")
        else:
            turns.append((speaker, content))

    return " ".join(f"[L{speaker}]: {content}" for speaker, content in turns)


def clean_chunk_text(text: str) -> str:
    return sanitize_transcription(text)


def _relevance_score(text: str) -> int:
    score = 0
    patterns = (
        (r"\d|R\$|%", 120),
        (r"\?", 90),
        (r"\b(?:não|nunca|sem)\b", 90),
        (r"\b(?:decid|acord|aprov|defin|combin)\w*\b", 120),
        (r"\b(?:ação|enviar|entregar|fazer|agendar|responsável)\w*\b", 100),
        (r"\b(?:prazo|hoje|amanhã|segunda|terça|quarta|quinta|sexta|data)\w*\b", 110),
        (r"\b(?:erro|problema|risco|dúvida|pendente|bloqueio)\w*\b", 100),
        (r"\b(?:evidência|cliente|contrato|proposta|orçamento)\w*\b", 60),
    )
    for pattern, weight in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            score += weight
    return score + min(len(text.split()), 30)


def select_relevant_transcription(text: str, retention_ratio: float) -> str:
    if not 0 < retention_ratio <= 1:
        raise ValueError("A taxa de retenção deve ser maior que 0 e menor ou igual a 1.")
    cleaned = clean_transcription(text)
    if retention_ratio == 1 or not cleaned:
        return cleaned

    matches = list(_COMPACT_SPEAKER_PATTERN.finditer(cleaned))
    if not matches:
        return cleaned
    turns: list[tuple[int, str, int, int]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(cleaned)
        turn = cleaned[match.start():end].strip()
        token_count = len(re.findall(r"\w+|[^\w\s]", turn, re.UNICODE))
        turns.append((index, turn, token_count, _relevance_score(turn)))

    total_tokens = sum(turn[2] for turn in turns)
    budget = max(1, round(total_tokens * retention_ratio))
    selected: list[tuple[int, str, int, int]] = []
    used = 0
    for turn in sorted(turns, key=lambda value: (-value[3], value[0])):
        if selected and used + turn[2] > budget:
            if turn[3] < 100 or used >= budget:
                continue
        selected.append(turn)
        used += turn[2]
        if used >= budget:
            break
    selected.sort(key=lambda value: value[0])
    return " ".join(turn[1] for turn in selected)


def rank_chunk_indices_for_partial(chunks: list[str], limit: int) -> list[int]:
    """Prioritize high-signal chunks while sampling the whole timeline."""
    if limit < 1 or not chunks:
        return []
    limit = min(limit, len(chunks))
    anchors = [0, len(chunks) // 2, len(chunks) - 1]
    required = []
    for index in anchors:
        if index not in required and len(required) < limit:
            required.append(index)

    ranked = sorted(
        range(len(chunks)),
        key=lambda index: (-_relevance_score(chunks[index]), index),
    )
    selected = list(required)
    for index in ranked:
        if index not in selected:
            selected.append(index)
        if len(selected) == limit:
            break

    # Process the strongest selected evidence first; index breaks ties stably.
    return sorted(
        selected,
        key=lambda index: (-_relevance_score(chunks[index]), index),
    )
