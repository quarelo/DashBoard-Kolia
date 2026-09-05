"""Rules that turn transcript text into motive codes, without an LLM.

Why rules and not the model: on this hardware the analysis model is a 1B, and it
classified these six sentences 3/6 right even with few-shot — it called "vamos
agendar a próxima reunião" a cancellation threat. A business score at coin-flip
accuracy is worse than none, because it invents churn. Rules are reviewable,
versioned, and give the same answer every run, which is the whole point of the
deterministic scoring layer.

The LLM path is not gone: when a model that can classify is available, the codes
it declares under the enum-constrained schema take precedence over these rules.

Reading the rules: a motive fires when any TRIGGER matches and no BLOCKER does.
Blockers exist because sales talk is full of hypotheticals — a prospect asking
"e se não der certo?" is an objection to answer, not a customer leaving. Without
that guard the four real transcripts in this dataset all scored churn, and every
one of them is a prospecting call with no customer to lose.

Text is normalised (lowercase, accents stripped) before matching, so a rule does
not have to spell out every accented variant.
"""
import re
import unicodedata

from src.app.services.scoring_service import ChurnMotive, OpportunityMotive


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped)


# A hypothetical or a demo narrated by the seller is not a fact about the client.
# These are checked against the whole sentence, not just near the trigger.
HYPOTHETICAL = re.compile(
    r"\b(?:se n[ao]o|caso n[ao]o|e se\b|imagin[ae]|suponha|por exemplo|"
    r"vamos supor|potencial de|hipotes|digamos)\b"
)

CHURN_RULES: dict[str, dict] = {
    ChurnMotive.AMEACA_CANCELAMENTO.value: {
        # Explicit enough to survive a conditional: "se não melhorar vamos
        # encerrar o contrato" is a customer committing to leave.
        "survives_hypothetical": True,
        "triggers": [r"\bcancel\w*", r"\brescind\w*", r"\brescis\w*",
                     r"\bencerrar (?:o )?contrato", r"\bnao (?:vamos )?renovar",
                     r"\bsair d[ao] (?:contrato|servico|plataforma)"],
        "blockers": [
            # "pedido cancelado" is an operational metric, not the account leaving.
            r"\b(?:pedido|ordem|fatura|nota|agendamento)s? (?:foi |foram )?cancelad",
        ],
    },
    ChurnMotive.INSATISFACAO_EXPLICITA.value: {
        "triggers": [r"\binsatisfeit\w*", r"\binsatisfac\w*", r"\bdesconten\w*",
                     r"\bfrustra\w*", r"\bdecepcion\w*", r"\bdecepc\w*",
                     r"\bnao (?:estamos|estao) satisfeit"],
        "blockers": [],
    },
    ChurnMotive.MENCAO_CONCORRENTE.value: {
        "triggers": [r"\bconcorren\w*", r"\boutro fornecedor", r"\boutra empresa",
                     r"\bproposta d[ao] \w+ tambem", r"\bavaliando (?:outras|outra)"],
        "blockers": [],
    },
    ChurnMotive.RECLAMACAO_PRODUTO.value: {
        "triggers": [r"\btrava\w*", r"\bda erro", r"\bdeu erro", r"\bcai (?:toda|todo)",
                     r"\bnao funciona", r"\bbug\w*", r"\blentid\w*", r"\bfora do ar"],
        "blockers": [],
    },
    ChurnMotive.INATIVIDADE_PROLONGADA.value: {
        # Needs an explicit stretch of time; "sem comprar" alone is ambiguous.
        # Needs an explicit stretch of time, spelled or in digits; "sem comprar"
        # on its own is ambiguous.
        "triggers": [r"\b\d+\s*(?:dias|meses|anos)\s+sem\s+(?:comprar|usar|acessar|retorno)",
                     r"\bnao (?:usam|acessam|compram|retornam)\b.{0,30}\bh[ao]\s+\w+",
                     r"\bsem (?:uso|acesso|compra|retorno)\b.{0,20}\bh[ao]\s+\w+"],
        "blockers": [],
    },
}

OPPORTUNITY_RULES: dict[str, dict] = {
    OpportunityMotive.PEDIDO_EXPANSAO.value: {
        "triggers": [r"\bampliar\w*", r"\bexpandir\w*", r"\bmais licenc\w*",
                     r"\baumentar (?:o )?(?:contrato|escopo|plano)",
                     r"\bnovas lojas", r"\boutras unidades"],
        "blockers": [],
    },
    OpportunityMotive.MENCAO_BUDGET.value: {
        # A figure with a currency or an explicit budget word; a bare number is not.
        "triggers": [r"\br\$\s*\d", r"\b\d[\d.,]*\s*(?:mil|milh[ao]es)\b",
                     r"\borcamento\b", r"\bverba\b", r"\binvestiment\w*"],
        "blockers": [],
    },
    OpportunityMotive.PRAZO_DEFINIDO.value: {
        "triggers": [r"\b\d+\s*dias\b", r"\bate (?:sexta|segunda|terca|quarta|quinta)",
                     r"\bamanha\b", r"\bproxima semana", r"\bmes que vem",
                     r"\b\d{1,2}/\d{1,2}"],
        "blockers": [],
    },
    OpportunityMotive.INTERESSE_NOVO_MODULO.value: {
        "triggers": [r"\bnovas solucoes", r"\bnovo modulo", r"\boutro produto",
                     r"\bquerem fazer teste", r"\bfazer um teste", r"\btrial\b",
                     r"\bconhecer (?:a |o )?(?:ferramenta|solucao|plataforma)"],
        "blockers": [],
    },
    OpportunityMotive.ELOGIO_CLIENTE.value: {
        "triggers": [r"\bexcelente\b", r"\botimo\b", r"\bmuito bom\b",
                     r"\bgostamos muito", r"\batendeu (?:bem|super)",
                     r"\bmuda bastante", r"\bfaz sentido pra (?:gente|nos)"],
        "blockers": [],
    },
}


def _fires(sentence: str, rule: dict) -> bool:
    if any(re.search(pattern, sentence) for pattern in rule["blockers"]):
        return False
    return any(re.search(pattern, sentence) for pattern in rule["triggers"])


def _motives(text: str, rules: dict[str, dict], guard_hypothetical: bool) -> list[str]:
    """Codes whose rules fire somewhere in the text, in catalogue order."""
    found: list[str] = []
    # Sentence-level so a blocker in one clause cannot mask a real signal elsewhere.
    sentences = [s for s in re.split(r"[.!?\n]+", normalize(text)) if s.strip()]
    for code, rule in rules.items():
        for sentence in sentences:
            hypothetical = guard_hypothetical and HYPOTHETICAL.search(sentence)
            if hypothetical and not rule.get("survives_hypothetical"):
                continue
            if _fires(sentence, rule):
                found.append(code)
                break
    return found


def churn_motives(text: str) -> list[str]:
    """Churn needs a real customer signal, so hypotheticals are excluded."""
    return _motives(text, CHURN_RULES, guard_hypothetical=True)


def opportunity_motives(text: str) -> list[str]:
    """A budget or deadline stated inside a hypothetical is still a real datum."""
    return _motives(text, OPPORTUNITY_RULES, guard_hypothetical=False)
