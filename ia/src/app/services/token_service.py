import re

_TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def count_tokens(text: str) -> int:
    return len(_TOKEN_PATTERN.findall(text)) if text else 0


def split_text_by_tokens(text: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    if max_tokens <= 0:
        raise ValueError("max_tokens must be greater than zero")
    if overlap_tokens < 0:
        raise ValueError("overlap_tokens must not be negative")
    if overlap_tokens >= max_tokens:
        raise ValueError("overlap_tokens must be smaller than max_tokens")
    tokens = _TOKEN_PATTERN.findall(text)
    if not tokens:
        return []
    if len(tokens) <= max_tokens:
        return [text.strip()]
    chunks, start = [], 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        chunks.append(" ".join(tokens[start:end]).strip())
        if end >= len(tokens):
            break
        start = end - overlap_tokens
    return chunks
