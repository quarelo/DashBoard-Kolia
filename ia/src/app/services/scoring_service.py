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


def infer_churn_motives(text: str) -> list[str]:
    """
    Infer churn motives from text using heuristic patterns.

    This function provides a fallback when enum codes are not available,
    allowing compatibility with LLM outputs that return free text.

    Args:
        text: Churn signal text to analyze.

    Returns:
        List of inferred ChurnMotive codes (as strings).

    Note: This is deterministic but uses pattern matching. Prefer
    direct enum input from LLM when available.
    """
    text_lower = text.lower()
    motives = []

    # Threat of cancellation: explicit mentions of ending contract
    if any(word in text_lower for word in [
        "cancel", "ameaç", "encerr", "término",
        "rescis", "rescindir"
    ]):
        motives.append(ChurnMotive.AMEACA_CANCELAMENTO.value)

    # Explicit dissatisfaction: dissatisfied customer signals
    if any(word in text_lower for word in [
        "insatisfeit", "desconten", "decepç", "decepcion",
        "frustrac", "frustr"
    ]):
        motives.append(ChurnMotive.INSATISFACAO_EXPLICITA.value)

    # Competitor mention: customer considering alternatives
    if any(word in text_lower for word in [
        "concorrente", "concorrência", "alternativa",
        "outro fornecedor", "mudar de", "trocar de", "trocar para",
        "solução mais barata"
    ]):
        motives.append(ChurnMotive.MENCAO_CONCORRENTE.value)

    # Product complaint: specific product issues
    if any(word in text_lower for word in [
        "lentid", "lento", "falha", "erro", "problema",
        "não funciona", "bug", "crash"
    ]):
        motives.append(ChurnMotive.RECLAMACAO_PRODUTO.value)

    # Inactivity or retention risk: potential loss if value not found
    if any(phrase in text_lower for phrase in [
        "potencial de perda", "potencial de não", "risco de perder",
        "não retorn", "não retid", "deixar de", "não seguir", "inativ"
    ]):
        # This covers cases like:
        # - "Potencial de perda se os clientes não encontrarem valor"
        # - "Potencial de não seguir com a proposta"
        # - "Risco de não retornar se não ver resultado"
        motives.append(ChurnMotive.INATIVIDADE_PROLONGADA.value)

    return motives


def infer_opportunity_motives(text: str) -> list[str]:
    """
    Infer opportunity motives from text using heuristic patterns.

    This function provides a fallback when enum codes are not available,
    allowing compatibility with LLM outputs that return free text.

    Args:
        text: Opportunity signal text to analyze.

    Returns:
        List of inferred OpportunityMotive codes (as strings).

    Note: This is deterministic but uses pattern matching. Prefer
    direct enum input from LLM when available.
    """
    text_lower = text.lower()
    motives = []

    # Expansion request: customer wants to grow/expand
    if any(phrase in text_lower for phrase in [
        "expandir", "crescer", "adicionar", "aumentar", "novo",
        "mais licença", "mais usuário", "escalar", "ampliar"
    ]):
        motives.append(OpportunityMotive.PEDIDO_EXPANSAO.value)

    # Budget mention: financial resources discussed
    if any(phrase in text_lower for phrase in [
        "r$", "mil", "milhão", "investimento", "orçamento", "budget",
        "reais", "custo", "preço"
    ]):
        motives.append(OpportunityMotive.MENCAO_BUDGET.value)

    # Timeline defined: customer set specific schedule
    if any(phrase in text_lower for phrase in [
        "segunda", "terça", "quarta", "quinta", "sexta",
        "janeiro", "fevereiro", "março", "abril", "maio", "junho",
        "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
        "semana", "mês", "ano", "hoje", "amanhã", "próximo",
        "prazo", "data", "deadline"
    ]):
        motives.append(OpportunityMotive.PRAZO_DEFINIDO.value)

    # New module interest: customer interested in new features/products
    if any(phrase in text_lower for phrase in [
        "módulo", "funcionalidad", "feature", "novo produto",
        "integração", "upgrade", "versão"
    ]):
        motives.append(OpportunityMotive.INTERESSE_NOVO_MODULO.value)

    # Customer praise: positive feedback about product/service
    if any(word in text_lower for word in [
        "elogio", "gostou", "adorou", "excelente", "ótimo",
        "maravilhos", "fantásti", "incrível", "satisfeit"
    ]):
        motives.append(OpportunityMotive.ELOGIO_CLIENTE.value)

    return motives
