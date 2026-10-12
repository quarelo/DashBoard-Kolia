"""Speech-to-text spellings of TOTVS product names, mapped to the catalogue
spelling, so chunks and product grounding see the name the catalogue uses.

Only variants that cannot be an ordinary Portuguese word belong here: "fluir"
is a real verb, so it is not mapped to Fluig even though the transcriber
sometimes writes it that way. Order matters: later patterns see the output of
earlier ones (Totus -> TOTVS happens before the Transmite rule).
"""
import re

_ALIASES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(pattern, re.IGNORECASE), replacement)
    for pattern, replacement in (
        (r"\b(?:totos|totus|tots)\b", "TOTVS"),
        (r"\bproteus\b", "Protheus"),
        # "Transmit" alone is how the product is said; naming it in full keeps
        # it from reading as the Portuguese verb "transmite".
        (r"\b(?:totvs\s+)?transmit\b", "TOTVS Transmite"),
        (r"\b(?:appflux|openflux)\b", "Upflux"),
    )
]


def normalize_aliases(text: str) -> str:
    for pattern, replacement in _ALIASES:
        text = pattern.sub(replacement, text)
    return text
