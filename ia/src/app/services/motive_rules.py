"""Rules that turn transcript text into motive codes, without an LLM.

Why rules and not the model: on this hardware the analysis model is a 1B, and it
classified these six sentences 3/6 right even with few-shot — it called "vamos
agendar a próxima reunião" a cancellation threat. A business score at coin-flip
accuracy is worse than none, because it invents churn. Rules are reviewable,
versioned, and give the same answer every run, which is the whole point of the
deterministic scoring layer.

The LLM path is not gone: when a model that can classify is available, the codes
it declares under the enum-constrained schema take precedence over these rules.

Reading the rules: a motive fires when any TRIGGER matches in a clause where no
BLOCKER and no ABSENCE match.
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

# Dizer que um sinal ESTÁ AUSENTE não é o sinal. O modelo de análise escreve
# exatamente isso sob a tag CHURN numa reunião tranquila, e "não há menção de
# insatisfação, ameaça de cancelamento ou comparação com concorrentes" carrega as
# três palavras mais caras do catálogo — as regras liam as três como presentes:
# 50 + 30 + 25 = 105, capado em 100. Como estoura o teto, toda frase de negação
# pousava em exatamente 100 e ocupava o topo do ranking: 10 das 25 reuniões com
# churn 100 eram isso, e enchiam o Top 5 da dashboard.
#
# Por que não um "não" genérico: `não funciona`, `não vamos renovar` e `não
# estamos satisfeitos` são gatilhos legítimos. A guarda tem que nomear a
# ausência, então casa um verbo de existência negado ou um substantivo explícito
# de "nenhum sinal". Medido sobre os 305 fatos CHURN distintos do banco, uma
# forma mais larga que aceitasse `nenhum\w*` ou `não identificad\w*` soltos calou
# três sinais reais — "insatisfação ... não utiliza nenhum sistema ERP" e
# "lacunas de conhecimento não identificadas na proposta" —, e é por isso que os
# dois exigem um substantivo de sinal depois.
ABSENCE = re.compile(
    r"\b(?:"
    r"nao h[ao]\b|nao houve\b|nao havia\b|nao existe(?:m)?\b"
    r"|nao (?:foi|foram|e) (?:mencionad|identificad|relatad|citad|apresentad|"
    r"demonstrad|observad|detectad|registrad|constatad|verificad)\w*"
    r"|nao (?:apresenta|apresentou|demonstra|demonstrou|indica|indicam|evidencia)\b"
    r"|nenhum\w*\s+(?:mencao|sinal|sinais|indicio\w*|evidencia\w*|ameaca|intencao|"
    r"risco|reclamacao|insatisfacao|queixa)"
    r"|sem (?:mencao|sinais|sinal|indicio\w*|evidencia\w*|intencao|risco|ameaca)"
    r"|ausencia de|baixa probabilidade|nada que indique"
    r")"
)

# Cláusulas, não só frases: o modelo junta um sinal real a uma negação com uma
# adversativa, e uma guarda do tamanho da frase jogaria os dois fora — "houve
# desentendimento ... frustração e descontentamento futuro, mas não houve menção
# explícita de cancelamento" é insatisfação 30, não insatisfação + ameaça 80.
CLAUSE_SPLIT = re.compile(r"[.!?\n;]+|\b(?:mas|porem|contudo|entretanto|todavia)\b")

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
        # Named competitors count the same as the generic word: a client saying
        # "hoje usamos SAP" carries the same signal as "usamos um concorrente",
        # but only the generic phrasing fired before. "senior sistemas" is the
        # one that needs the full phrase — the bare word is also the common
        # Portuguese adjective ("gerente sênior"), which normalize() collapses
        # onto the same text and would otherwise fire on every senior job title.
        "triggers": [r"\bconcorren\w*", r"\boutro fornecedor", r"\boutra empresa",
                     r"\bproposta d[ao] \w+ tambem", r"\bavaliando (?:outras|outra)",
                     r"\bsap\b", r"\boracle\b", r"\bsankhya\b", r"\bsenior sistemas\b",
                     r"\bomie\b", r"\bdynamics\b"],
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
    # Cláusula a cláusula, para que um blocker numa delas não mascare um sinal real
    # em outra.
    sentences = [s for s in CLAUSE_SPLIT.split(normalize(text)) if s.strip()]
    for code, rule in rules.items():
        for sentence in sentences:
            # A ausência vale acima de `survives_hypothetical`: "não há ameaça de
            # cancelamento" é negação, não um compromisso condicional de sair.
            if ABSENCE.search(sentence):
                continue
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
    """A budget or deadline stated inside a hypothetical is still a real datum.

    A ausência, não: "não há menção de expansão de contrato ou novo módulo" não é
    uma oportunidade, e a `ABSENCE` vale aqui também. Mede pouco deste lado — 1 de
    856 fatos OPORTUNIDADE do banco —, porque o vocabulário de gatilho raramente se
    repete numa frase de recusa, mas o mecanismo é o mesmo do churn.
    """
    return _motives(text, OPPORTUNITY_RULES, guard_hypothetical=False)
