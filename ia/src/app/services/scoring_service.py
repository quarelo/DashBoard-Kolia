"""
Deterministic risk and opportunity scoring service.

Provides catalog-based scoring for churn risk and opportunity scores,
eliminating dependency on regex-based vocabulary matching.

Each motive has a fixed point value. Score is the sum of identified
motives, capped at 100. Identical motives count only once.
"""

from enum import Enum
from typing import NamedTuple


class ChurnMotive(str, Enum):
    """Churn risk motives with point values."""
    AMEACA_CANCELAMENTO = "AMEACA_CANCELAMENTO"  # 50
    INSATISFACAO_EXPLICITA = "INSATISFACAO_EXPLICITA"  # 30
    MENCAO_CONCORRENTE = "MENCAO_CONCORRENTE"  # 25
    RECLAMACAO_PRODUTO = "RECLAMACAO_PRODUTO"  # 15
    INATIVIDADE_PROLONGADA = "INATIVIDADE_PROLONGADA"  # 10


class OpportunityMotive(str, Enum):
    """Commercial opportunity motives with point values."""
    PEDIDO_EXPANSAO = "PEDIDO_EXPANSAO"  # 40
    MENCAO_BUDGET = "MENCAO_BUDGET"  # 30
    PRAZO_DEFINIDO = "PRAZO_DEFINIDO"  # 25
    INTERESSE_NOVO_MODULO = "INTERESSE_NOVO_MODULO"  # 20
    ELOGIO_CLIENTE = "ELOGIO_CLIENTE"  # 15


# Fixed point values for each motive
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


class ScoringResult(NamedTuple):
    """Scoring result with score and identified motives."""
    score: int
    motives: list[str]  # Enum string values of identified motives


def calculate_churn_risk(motives: list[str]) -> ScoringResult:
    """
    Calculate churn risk score from list of motive codes.

    Args:
        motives: List of ChurnMotive enum values (as strings).

    Returns:
        ScoringResult with score (0-100) and unique motives identified.

    Deterministic: same input always produces same output.
    Unknown motives are silently ignored.
    """
    unique_motives = []
    seen = set()

    for motive_str in motives:
        if motive_str in seen:
            continue
        # Verify motive exists in enum
        try:
            ChurnMotive(motive_str)
            unique_motives.append(motive_str)
            seen.add(motive_str)
        except ValueError:
            # Unknown motive code ignored without error
            continue

    if not unique_motives:
        return ScoringResult(score=0, motives=[])

    # Sum points from identified motives
    total = sum(CHURN_POINTS[ChurnMotive(m)] for m in unique_motives)
    score = min(100, total)

    return ScoringResult(score=score, motives=unique_motives)


def calculate_opportunity_score(motives: list[str]) -> ScoringResult:
    """
    Calculate opportunity score from list of motive codes.

    Args:
        motives: List of OpportunityMotive enum values (as strings).

    Returns:
        ScoringResult with score (0-100) and unique motives identified.

    Deterministic: same input always produces same output.
    Unknown motives are silently ignored.
    """
    unique_motives = []
    seen = set()

    for motive_str in motives:
        if motive_str in seen:
            continue
        # Verify motive exists in enum
        try:
            OpportunityMotive(motive_str)
            unique_motives.append(motive_str)
            seen.add(motive_str)
        except ValueError:
            # Unknown motive code ignored without error
            continue

    if not unique_motives:
        return ScoringResult(score=0, motives=[])

    # Sum points from identified motives
    total = sum(OPPORTUNITY_POINTS[OpportunityMotive(m)] for m in unique_motives)
    score = min(100, total)

    return ScoringResult(score=score, motives=unique_motives)