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
    # Spans, not just the token strings: chunks are sliced out of the original
    # text so punctuation and spacing survive. Re-joining tokens with " " used to
    # rewrite "[L67]:" as "[ L67 ] :" and "sexta-feira" as "sexta - feira", and
    # that mangled wording then showed up in every quoted piece of evidence.
    spans = [match.span() for match in _TOKEN_PATTERN.finditer(text)]
    if not spans:
        return []
    tokens = [text[start:end] for start, end in spans]
    if len(tokens) <= max_tokens:
        return [text.strip()]
    chunks, start = [], 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        if end < len(tokens):
            minimum_boundary = start + max(1, (max_tokens + 1) // 2)
            sentence_boundaries = [
                index + 1
                for index in range(minimum_boundary - 1, end)
                if tokens[index] in {".", "!", "?", ";"}
            ]
            if sentence_boundaries:
                end = sentence_boundaries[-1]
        chunks.append(text[spans[start][0]:spans[end - 1][1]].strip())
        if end >= len(tokens):
            break
        start = end - overlap_tokens
    return chunks
