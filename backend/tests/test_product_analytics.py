"""As leituras de produto que não precisam de banco: a natureza de um gap, as
cinco médias do perfil de qualidade e as três marcas do Gráfico de Produto.

`product_insights`, `product_quality_profile` e `executive_overview` inteiros
passam por Postgres (o `WHERE` do recorte é JSONB), então o que está fixado aqui
são as funções puras por trás deles — é onde mora a regra, e é o que quebraria
calado numa mudança de vocabulário, de denominador ou de unidade de contagem.
"""
from types import SimpleNamespace

import pytest

from services.analysis_read import (
    GAP_NATURE_UNCLASSIFIED, _meeting_marks, _quality_metrics, classify_gap,
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


# --- marcas do Gráfico de Produto -------------------------------------------


def test_meeting_marks_conta_reuniao_e_nao_item():
    """A regra que o gráfico mostra: uma reunião com três reclamações é **uma**
    reunião com reclamação. Se isto voltar a contar itens, a barra volta a medir
    o quanto a IA detalhou a reunião em vez de em quantas conversas o assunto
    apareceu."""
    marcas = _meeting_marks({
        "problemas_identificados": ["p1", "p2", "p3"],
        "gap_produto": ["g1"],
        "sentimento": {"classificacao": "positivo"},
        "feedback_produto": ["f1", "f2"],
    })

    assert marcas == {"reclamacoes": True, "gaps": True, "elogios": True}


def test_meeting_marks_sem_nada_nao_marca_nada():
    assert _meeting_marks({}) == {
        "reclamacoes": False, "gaps": False, "elogios": False,
    }


@pytest.mark.parametrize("classificacao, esperado", [
    ("positivo", True),
    ("misto", False),
    ("negativo", False),
    ("neutro", False),
])
def test_meeting_marks_elogio_exige_sentimento_positivo(classificacao, esperado):
    """`feedback_produto` não carrega polaridade própria — só vira elogio quando
    o sentimento geral da reunião já foi classificado como positivo. Sem isso,
    "o preço está alto" entraria como elogio ao produto."""
    marcas = _meeting_marks({
        "feedback_produto": ["o módulo fiscal atende"],
        "sentimento": {"classificacao": classificacao},
    })

    assert marcas["elogios"] is esperado


def test_meeting_marks_ignora_final_summary_nao_dicionario():
    """A coluna é JSONB e pode voltar como lista ou nulo numa análise antiga; o
    Gráfico de Produto não pode quebrar por isso."""
    assert _meeting_marks(None)["gaps"] is False
    assert _meeting_marks([])["reclamacoes"] is False


def test_meeting_marks_e_a_unidade_das_duas_telas():
    """`executive_overview` (Gráfico de Produto) e `product_insights`
    (`saude_mensal`) contam pela mesma função, de propósito: as duas telas usam
    as mesmas três palavras e não podem querer dizer coisas diferentes com
    elas. `natureza_gaps` é a exceção documentada — lá a unidade é o gap.

    Este teste fixa o contrato que as duas consomem: três chaves, booleanas,
    com os nomes que viram campos na resposta.
    """
    marcas = _meeting_marks({"gap_produto": ["g1", "g2", "g3"]})

    assert set(marcas) == {"reclamacoes", "gaps", "elogios"}
    assert all(isinstance(value, bool) for value in marcas.values())
    # Três gaps, uma reunião — é o que o mês soma, e o que a barra soma.
    assert int(marcas["gaps"]) == 1
