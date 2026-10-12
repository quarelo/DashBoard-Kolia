"""Which transcript speakers are TOTVS staff, from how they introduce themselves.

Transcripts only tag speakers by number, and the model was reading seller lines as
the client's: a seller's "plug and play, sem CAPEX" became client feedback, and a
seller's pre-meeting price talk became the client's budget. Sellers do introduce
themselves ("sou aqui do comercial da Totvs"), and transcription spells the brand
as Totvs, Totos, Totus or Tots.
"""
import re

_TURN_TAG = re.compile(r"\[\s*(?:LOCUTOR\s*|L)(\d+)\s*\]\s*:?", re.IGNORECASE)
_TOTVS = r"tot(?:vs|os|us|s)"
# First person, then either a sales role (or "aqui"/"investida") tied to the brand
# by a preposition, or a title only a seller carries. No comma in the gap, so a
# client's "sou aqui da [EMPRESA], cliente da Totvs" does not count.
# ponytail: phrase heuristic; a seller who never introduces themselves is missed.
_VENDOR_INTRO = re.compile(
    r"\b(?:sou|somos)\b[^.?!,]{0,60}?(?:"
    r"\b(?:comercial|especialista|executiv[oa]|consultor[a]?|gerente\s+de\s+contas|"
    r"aqui|investida)\b[^.?!,]{0,40}?\b(?:d[ao]|pel[ao]|n[ao])\s+(?:\S+\s+){0,2}?"
    + _TOTVS + r"\b"
    r"|\bexecutiv[oa]\s+de\s+(?:contas|neg[óo]cios)\b|\bgerente\s+de\s+contas\b)",
    re.IGNORECASE,
)


def detect_vendor_speakers(transcript: str) -> list[str]:
    """Speaker numbers ("43") whose turns self-identify as TOTVS or partner staff,
    in order of first appearance. Accepts `[LOCUTOR 43]:` and `[L43]:` tags."""
    parts = _TURN_TAG.split(transcript or "")
    vendors: list[str] = []
    for number, turn in zip(parts[1::2], parts[2::2]):
        if number not in vendors and _VENDOR_INTRO.search(turn):
            vendors.append(number)
    return vendors


def format_speaker_context(speakers: list[str]) -> str | None:
    """One prompt line naming the TOTVS speakers and what their lines are not."""
    if not speakers:
        return None
    names = ", ".join(f"L{number}" for number in speakers)
    return (
        f"Locutores da TOTVS (vendedores/especialistas): {names}. Os demais são do "
        "cliente. Feedback, elogio, orçamento, persona, dúvidas e sinais de churn ou "
        "oportunidade só contam quando ditos pelo cliente; o que os locutores da "
        "TOTVS dizem é a oferta da TOTVS."
    )
