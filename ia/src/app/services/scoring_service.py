"""Deterministic risk and opportunity scoring.

The codes come from the model's declaration (or, failing that, the rules in
`motive_rules.py`); this module turns codes into a 0-100 number.

Two things shape the number, and both exist because the straight sum saturated.
Measured on 198 analyses in 2026-10-09: opportunity had median 90, 65% at or above
90, and 42 meetings at exactly 100 — because the three commonest codes were worth
20 + 40 + 30 = 90 on their own, and a code counted the same whether the meeting
mentioned it once in twenty chunks or all the way through. The median tracked the
number of chunks (20 for one chunk, 90 from the third on), so the score measured
meeting length.

1. **Weight by evidence, not by presence.** A code backed by a quarter of the
   chunks, or by a literal quote the rules confirm, counts whole; a single mention
   in a long meeting counts less.
2. **Diminishing returns from the third code.** The two strongest signals count
   whole, the third halves, the fourth quarters. Keeps the spread (a flat discount
   compressed every meeting into 40-64) and removes the automatic ceiling.

The weights themselves live in `ai.scoring_weights`, editable by the commercial
team; the tables here are the fallback used when that table is unreachable or
empty, and the values match what the migration seeds.
"""

from enum import Enum
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


class ChurnMotive(str, Enum):
    """Churn risk motives."""
    AMEACA_CANCELAMENTO = "AMEACA_CANCELAMENTO"
    INSATISFACAO_EXPLICITA = "INSATISFACAO_EXPLICITA"
    MENCAO_CONCORRENTE = "MENCAO_CONCORRENTE"
    RECLAMACAO_PRODUTO = "RECLAMACAO_PRODUTO"
    INATIVIDADE_PROLONGADA = "INATIVIDADE_PROLONGADA"


class OpportunityMotive(str, Enum):
    """Commercial opportunity motives."""
    PEDIDO_EXPANSAO = "PEDIDO_EXPANSAO"
    MENCAO_BUDGET = "MENCAO_BUDGET"
    PRAZO_DEFINIDO = "PRAZO_DEFINIDO"
    INTERESSE_NOVO_MODULO = "INTERESSE_NOVO_MODULO"
    ELOGIO_CLIENTE = "ELOGIO_CLIENTE"


CHURN_SIDE = "CHURN"
OPPORTUNITY_SIDE = "OPPORTUNITY"

# Fallback point values, identical to the seed of migration 0010.
CHURN_POINTS = {
    ChurnMotive.AMEACA_CANCELAMENTO: 50,
    ChurnMotive.INSATISFACAO_EXPLICITA: 30,
    ChurnMotive.MENCAO_CONCORRENTE: 25,
    ChurnMotive.RECLAMACAO_PRODUTO: 15,
    ChurnMotive.INATIVIDADE_PROLONGADA: 10,
}

OPPORTUNITY_POINTS = {
    OpportunityMotive.PEDIDO_EXPANSAO: 40,
    OpportunityMotive.MENCAO_BUDGET: 30,
    OpportunityMotive.PRAZO_DEFINIDO: 25,
    OpportunityMotive.INTERESSE_NOVO_MODULO: 20,
    OpportunityMotive.ELOGIO_CLIENTE: 15,
}


class Ruler(NamedTuple):
    """The point table in force, with the version that identifies it.

    Version 0 is the fallback in this module: no row was read from the database.
    """
    version: int
    points: dict[str, int]


DEFAULT_RULER = Ruler(
    version=0,
    points={motive.value: points for motive, points in
            (*CHURN_POINTS.items(), *OPPORTUNITY_POINTS.items())},
)

# A code is worth its full weight when it shows up in at least this share of the
# meeting's chunks, or when the rules confirmed a literal quote for it. The share
# is the cheapest proxy for "the meeting is about this" that the stored summaries
# already answer; 25% is the value simulated in `docs/scoring-calibration-plan.md`
# and is meant to be re-tuned with `ia/scripts/score_sim.py` against the labelled
# set, not treated as settled.
EVIDENCE_SHARE_FLOOR = 0.25
# A single mention in a long meeting still counts — half, not nothing. Cutting it
# to zero was simulated and it silenced real signal: churn zeros went from 49 to 84.
WEAK_EVIDENCE_FACTOR = 0.5
# How many codes count whole before the discount starts.
FULL_WEIGHT_CODES = 2


class ScoringResult(NamedTuple):
    """Scoring result with score, identified motives and the ruler used."""
    score: int
    motives: list[str]
    ruler_version: int = 0


_cached_ruler: Ruler | None = None


def ruler(db: Session | None = None) -> Ruler:
    """The weights in force, from `ai.scoring_weights`, cached in memory.

    Reads once per process: the table changes when someone saves the screen, and
    that path calls `invalidate_ruler()`. Without a session (tests, scripts) or
    with an unreadable table, the fallback tables above answer, as version 0.
    """
    global _cached_ruler
    if _cached_ruler is None and db is not None:
        loaded = _load_ruler(db)
        if loaded is not None:
            _cached_ruler = loaded
    return _cached_ruler or DEFAULT_RULER


def invalidate_ruler() -> None:
    global _cached_ruler
    _cached_ruler = None


def _load_ruler(db: Session) -> Ruler | None:
    from src.app.models.scoring import ScoringWeight

    try:
        rows = db.execute(select(ScoringWeight)).scalars().all()
    except SQLAlchemyError:
        db.rollback()
        return None
    if not rows:
        return None
    return Ruler(
        version=max(row.ruler_version for row in rows),
        points={row.code: row.points for row in rows},
    )


def _unique_known(motives: list[str], enum: type[Enum]) -> list[str]:
    """Known codes, once each, in the order they were declared."""
    kept: list[str] = []
    for motive in dict.fromkeys(motives):
        try:
            enum(motive)
        except ValueError:
            # Unknown motive code ignored without error.
            continue
        kept.append(motive)
    return kept


def _score(codes: list[str], points: dict[str, int],
           evidence: dict[str, float] | None) -> int:
    weighted = []
    for code in codes:
        value = points.get(code)
        if value is None:
            continue
        share = 1.0 if evidence is None else evidence.get(code, 0.0)
        strength = 1.0 if share >= EVIDENCE_SHARE_FLOOR else WEAK_EVIDENCE_FACTOR
        weighted.append((value * strength, code))
    # Strongest signal first, so the discount falls on the weaker codes. The code
    # breaks ties, to keep the same input scoring the same every run.
    weighted.sort(key=lambda item: (-item[0], item[1]))
    total = 0.0
    for rank, (value, _) in enumerate(weighted):
        if rank < FULL_WEIGHT_CODES:
            total += value
        else:
            total += value * 0.5 ** (rank - FULL_WEIGHT_CODES + 1)
    # `int(total + 0.5)`, not `round`: Python rounds .5 to the even number, so a
    # score of 92.5 landed on 92 and 93.5 on 94 — a half point that moves the
    # number up or down depending on the neighbour is not something to explain on
    # a dashboard.
    return min(100, int(total + 0.5))


def calculate_churn_risk(
    motives: list[str],
    *,
    weights: Ruler | None = None,
    evidence: dict[str, float] | None = None,
) -> ScoringResult:
    """Churn score from motive codes.

    Args:
        motives: ChurnMotive values, as strings; repeats and unknowns are dropped.
        weights: the ruler in force; the fallback tables when omitted.
        evidence: code to share of the meeting's chunks that back it (1.0 for a
            code the rules confirmed). Omitted means every code counts whole.

    Deterministic: same input always produces same output.
    """
    table = weights or DEFAULT_RULER
    unique_motives = _unique_known(motives, ChurnMotive)
    if not unique_motives:
        return ScoringResult(score=0, motives=[], ruler_version=table.version)
    return ScoringResult(
        score=_score(unique_motives, table.points, evidence),
        motives=unique_motives,
        ruler_version=table.version,
    )


def calculate_opportunity_score(
    motives: list[str],
    *,
    weights: Ruler | None = None,
    evidence: dict[str, float] | None = None,
) -> ScoringResult:
    """Opportunity score from motive codes. Same contract as `calculate_churn_risk`."""
    table = weights or DEFAULT_RULER
    unique_motives = _unique_known(motives, OpportunityMotive)
    if not unique_motives:
        return ScoringResult(score=0, motives=[], ruler_version=table.version)
    return ScoringResult(
        score=_score(unique_motives, table.points, evidence),
        motives=unique_motives,
        ruler_version=table.version,
    )
