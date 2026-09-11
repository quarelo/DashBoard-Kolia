"""Known-answer cases for risco_churn and score_oportunidade.

    docker compose run --rm ia-service python -m scripts.evaluate_motives

Not ground truth: the transcripts and the expected codes were written by hand to
pin down failures seen while moving to qwen3.5:4b-q4_K_M (see docs/prompts.md).
Real calibration needs meetings labelled by the sales team; until then this is a
regression check to run after any change to the model or to MOTIVE_CATALOGUE.

Each case says which motive codes must be present and which must not. A case
fails on either. Exit status 1 when any case fails.
"""
import argparse
import json
import sys
from pathlib import Path

from src.app.core.config import settings
from src.app.services import llm_service
from src.app.services.analysis_service import _declared_unless_enumerated
from src.app.services.chunk_service import clean_transcription
from src.app.services.motive_rules import churn_motives, opportunity_motives
from src.app.services.scoring_service import (
    calculate_churn_risk,
    calculate_opportunity_score,
)
from src.app.services.token_service import split_text_by_tokens

CASES = {
    "demo com prospect interessado": {
        "must": {"opportunity": {"INTERESSE_NOVO_MODULO"}},
        "must_not": {"churn": {"AMEACA_CANCELAMENTO", "INSATISFACAO_EXPLICITA",
                               "MENCAO_CONCORRENTE", "RECLAMACAO_PRODUTO",
                               "INATIVIDADE_PROLONGADA"}},
        "text": (
            "[LOCUTOR 1]: Bom dia, obrigado por virem. A gente queria detalhar melhor "
            "as funcionalidades da ferramenta hoje.\n"
            "[LOCUTOR 2]: A gente tem bastante interesse, principalmente no módulo de "
            "força de vendas. Queríamos entender a aderência.\n"
            "[LOCUTOR 1]: Perfeito. Esse painel aqui mostra o ticket médio, e o "
            "vendedor consegue clonar o último pedido para agilizar.\n"
            "[LOCUTOR 2]: Isso faz muito sentido pra gente. Quantas licenças "
            "precisaríamos para 25 vendedores?"
        ),
    },
    "ameaça explícita de cancelamento": {
        "must": {"churn": {"AMEACA_CANCELAMENTO"}},
        "must_not": {},
        "text": (
            "[LOCUTOR 1]: Olha, vou ser bem direto com vocês. A diretoria está "
            "estudando encerrar o contrato na renovação.\n"
            "[LOCUTOR 2]: O que aconteceu?\n"
            "[LOCUTOR 1]: A gente está muito insatisfeito com o atendimento. O sistema "
            "dá erro toda vez que a gente tenta exportar o relatório de fechamento, "
            "e isso já faz três meses.\n"
            "[LOCUTOR 2]: Entendo, vamos priorizar isso.\n"
            "[LOCUTOR 1]: Se não melhorar até o fim do trimestre, vamos cancelar."
        ),
    },
    "avaliando concorrentes antes de renovar": {
        "must": {"churn": {"MENCAO_CONCORRENTE"}},
        "must_not": {"churn": {"INSATISFACAO_EXPLICITA"}},
        "text": (
            "[LOCUTOR 1]: Preciso ser transparente: a gente recebeu uma proposta da "
            "SAP na semana passada, e a Sankhya também veio conversar.\n"
            "[LOCUTOR 2]: Entendi. O que pesou na avaliação de vocês?\n"
            "[LOCUTOR 1]: O preço deles ficou bem abaixo. A gente está avaliando as "
            "duas opções antes de renovar."
        ),
    },
    "pedido de expansão com verba e prazo": {
        "must": {"opportunity": {"PEDIDO_EXPANSAO", "MENCAO_BUDGET"}},
        "must_not": {"churn": {"AMEACA_CANCELAMENTO", "INSATISFACAO_EXPLICITA"}},
        "text": (
            "[LOCUTOR 1]: A gente quer ampliar o contrato para as três novas lojas "
            "que abriram.\n"
            "[LOCUTOR 2]: Ótimo. Vocês têm orçamento definido?\n"
            "[LOCUTOR 1]: Temos R$ 180 mil aprovados para esse ano, e precisamos "
            "fechar até o fim do mês que vem. Também queríamos conhecer a "
            "plataforma de BI que vocês mencionaram."
        ),
    },
    "controle: usou concorrente no passado, satisfeito hoje": {
        "must": {},
        "must_not": {"churn": {"AMEACA_CANCELAMENTO", "INSATISFACAO_EXPLICITA"}},
        "text": (
            "[LOCUTOR 1]: Antes da TOTVS a gente usava o Omie, mas cresceu demais "
            "e não atendia mais.\n"
            "[LOCUTOR 2]: E hoje, como está?\n"
            "[LOCUTOR 1]: Hoje está ótimo, a equipe gostou muito do Protheus e a "
            "gente quer continuar."
        ),
    },
    "controle: reclamação leve de cliente satisfeito": {
        "must": {},
        "must_not": {"churn": {"AMEACA_CANCELAMENTO", "INSATISFACAO_EXPLICITA"}},
        "text": (
            "[LOCUTOR 1]: No geral estamos satisfeitos com o sistema.\n"
            "[LOCUTOR 2]: Que bom. Algum ponto de atenção?\n"
            "[LOCUTOR 1]: Só a tela de estoque que às vezes demora para carregar no "
            "fim do mês, mas nada que atrapalhe muito."
        ),
    },
    "controle: dado de inatividade na tela da demo": {
        "must": {},
        "must_not": {"churn": {"INATIVIDADE_PROLONGADA"}},
        "text": (
            "[LOCUTOR 1]: Aqui no painel eu consigo ver, por exemplo, que esse "
            "cliente está há 90 dias sem comprar, e esse outro há 190 dias.\n"
            "[LOCUTOR 2]: Interessante, isso ajudaria muito nossos vendedores a "
            "priorizar a carteira.\n"
            "[LOCUTOR 1]: Exato, e dá para filtrar por região."
        ),
    },
}


def score_case(text: str) -> dict:
    """Codes and scores the way build_compact_final_summary reaches them."""
    chunks = split_text_by_tokens(
        clean_transcription(text), settings.max_tokens_per_chunk, settings.overlap_tokens
    )
    declared_churn, declared_opportunity, points = [], [], []
    for chunk in chunks:
        summary = llm_service.generate_chunk_summary(chunk)
        declared_churn += summary.get("motivos_churn") or []
        declared_opportunity += summary.get("motivos_oportunidade") or []
        points += summary["pontos_chave"]

    trusted = settings.trust_declared_motives
    churn = (_declared_unless_enumerated(declared_churn) if trusted else []) or list(
        dict.fromkeys(c for p in points if p.startswith("CHURN:") for c in churn_motives(p)))
    opportunity = (_declared_unless_enumerated(declared_opportunity) if trusted else []) or list(
        dict.fromkeys(c for p in points if p.startswith("OPORTUNIDADE:")
                      for c in opportunity_motives(p)))
    return {
        "churn": churn,
        "opportunity": opportunity,
        "churn_score": calculate_churn_risk(churn).score,
        "opportunity_score": calculate_opportunity_score(opportunity).score,
    }


def check(case: dict, result: dict) -> list[str]:
    problems = []
    for side, codes in case["must"].items():
        missing = codes - set(result[side])
        if missing:
            problems.append(f"faltou {side}: {sorted(missing)}")
    for side, codes in case["must_not"].items():
        present = codes & set(result[side])
        if present:
            problems.append(f"não devia ter {side}: {sorted(present)}")
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report, failed = {}, 0
    for name, case in CASES.items():
        result = score_case(case["text"])
        problems = check(case, result)
        failed += bool(problems)
        report[name] = {**result, "problems": problems}
        status = "ok  " if not problems else "FAIL"
        print(f"{status} churn {result['churn_score']:>3}  oport. "
              f"{result['opportunity_score']:>3}  {name}"
              + (f"  -> {'; '.join(problems)}" if problems else ""), flush=True)
        if args.output:
            args.output.write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{len(CASES) - failed} de {len(CASES)} casos ok "
          f"(modelo {settings.chunk_model})")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
