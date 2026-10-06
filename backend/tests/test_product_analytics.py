"""As duas leituras da Página de Produto que não precisam de banco: a natureza
de um gap e as cinco médias do perfil de qualidade.

`product_insights` e `product_quality_profile` inteiros passam por Postgres (o
`WHERE` do recorte é JSONB), então o que está fixado aqui são as duas funções
puras por trás deles — é onde mora a regra, e é o que quebraria calado numa
mudança de vocabulário ou de denominador.
"""
from types import SimpleNamespace

import pytest

from services.analysis_read import (
    GAP_NATURE_UNCLASSIFIED, _quality_metrics, classify_gap,
)


@pytest.mark.parametrize("gap, esperado", [
    # Casos tirados dos gaps reais da carga, um por categoria.
    ("Integração nativa com Bling não é suportada, exigindo desenvolvimento externo", "Integração"),
    ("Automação completa de agendamento via WhatsApp vinculada ao sistema", "Automação de fluxo"),
    ("Limitação na criação de códigos de tributo adicionais vinculados a NCM", "Fiscal e tributário"),
    ("Ausência nativa de indicador específico para 'propostas faturadas'", "Relatório e indicador"),
    ("Ausência de controle detalhado de estoque por visita/paciente", "Controle e rastreabilidade"),
    ("Limites de processamento do CRM atual (10 requisições/minuto)", "Capacidade e performance"),
    ("Acessibilidade do layout para uso esporádico por médicos", "Usabilidade"),
    ("Prazo de implantação alinhado ao fim do ano", "Serviço e implantação"),
    # O que a taxonomia não cobre tem de dizer que não cobre, em vez de cair
    # numa categoria qualquer: o tamanho dessa fatia é o aviso na tela.
    ("Falta de líder de produção definido na empresa", GAP_NATURE_UNCLASSIFIED),
])
def test_classify_gap_nas_categorias_medidas(gap, esperado):
    assert classify_gap(gap) == esperado


def test_classify_gap_ignora_acento_e_caixa():
    """Os padrões são escritos sem acento justamente para não precisarem de uma
    variante por grafia; se a normalização sair, isto quebra."""
    assert classify_gap("INTEGRAÇÃO nativa faltando") == "Integração"
    assert classify_gap("integracao nativa faltando") == "Integração"


def test_integracao_vence_financeiro_em_gap_de_meio_de_pagamento():
    """A ordem de `_GAP_NATURE_RULES` é o critério de empate, e este é o caso
    que a motivou: "integração do meio de pagamento" é gap de integração, não de
    cobrança."""
    assert classify_gap("Integração total do meio de pagamento (100% do fluxo)") == "Integração"


def _row(produto, *, risco=0, oportunidade=0, sentimento="neutro", gaps=0, duvidas=0):
    return SimpleNamespace(final_summary={
        "produto": produto,
        "risco_churn": {"score": risco},
        "score_oportunidade": {"score": oportunidade},
        "sentimento": {"classificacao": sentimento},
        "gap_produto": [f"gap {i}" for i in range(gaps)],
        "duvidas_em_aberto": [f"duvida {i}" for i in range(duvidas)],
    })


def test_quality_metrics_media_as_cinco_metricas():
    rows = [
        _row(["A"], risco=80, oportunidade=40, sentimento="positivo", gaps=4, duvidas=2),
        _row(["A"], risco=20, oportunidade=60, sentimento="misto", gaps=0, duvidas=0),
    ]

    valores, total = _quality_metrics(rows)

    assert total == 2
    assert valores["risco_churn"] == 50.0
    assert valores["oportunidade"] == 50.0
    assert valores["satisfacao"] == 50.0  # uma das duas reuniões é positiva
    assert valores["gaps_por_reuniao"] == 2.0
    assert valores["duvidas_por_reuniao"] == 1.0


def test_quality_metrics_so_conta_reuniao_de_produto_unico():
    """O denominador tem de ser o mesmo do resto da página, senão a média do
    portfólio incluiria reunião multi-produto e de produto nenhum, e a diferença
    mediria isso em vez de medir o produto."""
    rows = [
        _row(["A"], risco=100),
        _row(["A", "B"], risco=0),   # multi-produto: fora
        _row([], risco=0),           # sem produto: fora
    ]

    valores, total = _quality_metrics(rows)

    assert total == 1
    assert valores["risco_churn"] == 100.0


def test_quality_metrics_sem_reuniao_nao_divide_por_zero():
    valores, total = _quality_metrics([])

    assert total == 0
    assert set(valores) == {
        "risco_churn", "oportunidade", "satisfacao",
        "gaps_por_reuniao", "duvidas_por_reuniao",
    }
    assert all(value == 0.0 for value in valores.values())
