"""Read, write and simulate the editable scoring ruler (`ai.scoring_weights`).

The screen that edits the weights needs more than the weights: calibrating in the
dark is what produced the saturated scores in the first place, so every motive is
served with how often it actually shows up in the analysed meetings, and a
proposed ruler can be simulated over the stored analyses before it is saved.

The declared codes are read from `chunk_summary` and counted in Python rather than
in a JSONB query: it is a few hundred small documents, the arithmetic is the same
on every dialect (the tests run on SQLite), and a `jsonb ? code` join is not
faster at this size.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.app.models.analysis import MeetingAnalysis, MeetingChunk
from src.app.models.scoring import ScoringWeight
from src.app.services.scoring_service import (
    CHURN_SIDE, OPPORTUNITY_SIDE, Ruler, calculate_churn_risk,
    calculate_opportunity_score, invalidate_ruler,
)

# Qual chave do `chunk_summary` guarda os códigos de cada lado.
_MOTIVE_KEY = {CHURN_SIDE: "motivos_churn", OPPORTUNITY_SIDE: "motivos_oportunidade"}


def _codes(summary: dict | None, side: str) -> list[str]:
    value = (summary or {}).get(_MOTIVE_KEY[side])
    return [code for code in value if isinstance(code, str)] if isinstance(value, list) else []


def declared_motives(db: Session) -> dict:
    """`{analysis_id: {side: {code: share of the meeting's chunks}}}`.

    Uma análise sem nenhum motivo também entra, com os lados vazios: score 0 é um
    resultado, e deixá-la fora esconderia os zeros da distribuição.
    """
    per_analysis: dict = {}
    chunks: dict = {}
    rows = db.execute(
        select(MeetingChunk.analysis_id, MeetingChunk.chunk_summary)
        .where(MeetingChunk.chunk_summary.is_not(None))
    ).all()
    for analysis_id, summary in rows:
        sides = per_analysis.setdefault(analysis_id, {CHURN_SIDE: {}, OPPORTUNITY_SIDE: {}})
        chunks[analysis_id] = chunks.get(analysis_id, 0) + 1
        for side in _MOTIVE_KEY:
            for code in set(_codes(summary, side)):
                sides[side][code] = sides[side].get(code, 0) + 1
    return {
        analysis_id: {
            side: {code: count / chunks[analysis_id] for code, count in codes.items()}
            for side, codes in sides.items()
        }
        for analysis_id, sides in per_analysis.items()
    }


def _frequency(db: Session) -> tuple[dict[str, int], int]:
    """Em quantas reuniões analisadas cada código apareceu, e quantas existem.

    Contado por reunião, não por chunk, porque é a unidade de que a tela fala:
    "aparece em 76% das reuniões analisadas".
    """
    counts: dict[str, int] = {}
    for sides in declared_motives(db).values():
        for codes in sides.values():
            for code in codes:
                counts[code] = counts.get(code, 0) + 1
    total = db.execute(
        select(func.count())
        .select_from(MeetingAnalysis)
        .where(MeetingAnalysis.final_summary.is_not(None))
    ).scalar_one()
    return counts, int(total or 0)


def list_weights(db: Session) -> dict:
    rows = db.execute(
        select(ScoringWeight).order_by(
            ScoringWeight.side, ScoringWeight.points.desc(), ScoringWeight.code)
    ).scalars().all()
    counts, total = _frequency(db)
    return {
        "ruler_version": max((row.ruler_version for row in rows), default=0),
        "analysed_meetings": total,
        # Saturation has one arithmetic cause: two codes that already reach the
        # ceiling together. The screen warns instead of refusing — a ruler where
        # the top two sum past 100 is a choice, just one worth seeing.
        "saturated_sides": sorted({
            row.side for row in rows
            if sum(sorted((other.points for other in rows if other.side == row.side),
                          reverse=True)[:2]) > 100
        }),
        "motives": [
            {
                "code": row.code,
                "side": row.side,
                "name": row.name,
                "description": row.description,
                "points": row.points,
                "meetings": counts.get(row.code, 0),
                "frequency": round(counts.get(row.code, 0) / total, 4) if total else 0.0,
                "updated_at": row.updated_at,
                "updated_by": row.updated_by,
            }
            for row in rows
        ],
    }


class UnknownMotiveError(ValueError):
    """A code that is not in the table: the code is the key and is not created here."""


def save_weights(db: Session, updates: list[dict], updated_by: str | None) -> dict:
    """Apply `[{code, points, name?, description?}]` and bump the ruler version.

    One version for the whole table, bumped once per save: a score carries the
    version that produced it, and a per-row counter would not identify the ruler a
    score was measured with. Stored scores are history and are not rewritten here
    (`scripts/rescore.py` does that, on request).
    """
    rows = {row.code: row for row in db.execute(select(ScoringWeight)).scalars()}
    unknown = [item["code"] for item in updates if item["code"] not in rows]
    if unknown:
        raise UnknownMotiveError(f"Código desconhecido: {', '.join(sorted(unknown))}")
    version = max((row.ruler_version for row in rows.values()), default=0) + 1
    for item in updates:
        row = rows[item["code"]]
        row.points = item["points"]
        if item.get("name"):
            row.name = item["name"]
        if item.get("description"):
            row.description = item["description"]
        row.updated_by = updated_by
    for row in rows.values():
        row.ruler_version = version
    db.commit()
    invalidate_ruler()
    return list_weights(db)


def _distribution(scores: list[int]) -> dict:
    if not scores:
        return {"count": 0}
    ordered = sorted(scores)
    middle = len(ordered) // 2
    median = (ordered[middle] if len(ordered) % 2
              else (ordered[middle - 1] + ordered[middle]) / 2)
    return {
        "count": len(ordered),
        "median": median,
        "mean": round(sum(ordered) / len(ordered), 1),
        "at_100": sum(1 for score in ordered if score == 100),
        "at_least_90": sum(1 for score in ordered if score >= 90),
        "zeros": sum(1 for score in ordered if score == 0),
    }


def simulate(db: Session, points: dict[str, int]) -> dict:
    """A distribuição que a régua proposta daria sobre as análises já gravadas.

    Sem escrever nada e sem chamar o modelo. A aproximação é uma só: o peso por
    evidência usa apenas a proporção de chunks que declararam o código, sem a
    confirmação por citação literal das regras, que exigiria reprocessar o texto.
    Isso só pode subestimar um score, nunca inflá-lo.
    """
    # -1 marca uma régua que não é a salva: nenhum score é gravado com ela.
    ruler = Ruler(version=-1, points=points)
    scores: dict[str, list[int]] = {CHURN_SIDE: [], OPPORTUNITY_SIDE: []}
    calculators = {CHURN_SIDE: calculate_churn_risk,
                   OPPORTUNITY_SIDE: calculate_opportunity_score}
    for sides in declared_motives(db).values():
        for side, calculate in calculators.items():
            shares = sides.get(side, {})
            scores[side].append(
                calculate(list(shares), weights=ruler, evidence=shares).score)
    return {"churn": _distribution(scores[CHURN_SIDE]),
            "opportunity": _distribution(scores[OPPORTUNITY_SIDE])}
