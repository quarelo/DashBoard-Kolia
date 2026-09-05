"""The rules replace an LLM that could not do this job on this hardware.

They exist to be reviewed by the business, so these tests are written as the
statements a reviewer would want to check, including the exact sentences that
the 1B model got wrong during evaluation.
"""
import pytest

from src.app.services.motive_rules import churn_motives, opportunity_motives
from src.app.services.scoring_service import (
    calculate_churn_risk, calculate_opportunity_score,
)

# The four distinct transcripts behind all 500 imported meetings. Every one is a
# prospecting call: there is no customer to lose, so churn must stay at zero.
PROSPECTING = [
    "L1 qual preço\nL2 trabalhamos pacotes customizados 15 20 mil mês\n"
    "L1 não der certo\nL2 gente oferece 60 dias trial gratuito\n"
    "L1 após 60 dias não veem resultado não cobramos nada",
    "L1 nossa solução conecta todas lojas plataforma\nL2 funciona\n"
    "L2 quanto tempo leva\nL1 30 dias máximo",
    "L1 boa tarde obrigado vir\nL2 gente está querendo conversar sobre novas soluções\n"
    "L2 controle inventário gente perde muito tempo isso",
    "L1 querem fazer teste\nL2 queria mas preciso conversar meu sócio\n"
    "L2 amanhã gente pode ter resposta\nL1 vou enviar proposta formal",
]


class TestChurnNeedsARealCustomerSignal:
    @pytest.mark.parametrize("transcript", PROSPECTING)
    def test_prospecting_calls_never_score_churn(self, transcript):
        assert calculate_churn_risk(churn_motives(transcript)).score == 0

    def test_sales_objection_is_not_churn(self):
        """'e se não der certo?' is an objection to answer, not a customer leaving.

        The previous scoring read this as churn on 250 of 500 meetings.
        """
        assert churn_motives("L1 não der certo\nL2 oferecemos 60 dias trial") == []

    def test_seller_hypothetical_is_not_churn(self):
        assert churn_motives("se não encontrarem valor podem deixar de comprar") == []

    def test_scheduling_a_meeting_is_not_churn(self):
        """The 1B model labelled this AMEACA_CANCELAMENTO during evaluation."""
        assert churn_motives("vamos agendar a próxima reunião") == []

    def test_cancelled_order_is_an_operational_metric_not_churn(self):
        assert churn_motives("o pedido foi cancelado pelo cliente") == []


class TestChurnFiresOnRealSignals:
    @pytest.mark.parametrize("sentence,expected", [
        ("se não melhorar vamos encerrar o contrato", "AMEACA_CANCELAMENTO"),
        ("estamos muito insatisfeitos com o atendimento", "INSATISFACAO_EXPLICITA"),
        ("recebemos uma proposta da concorrência", "MENCAO_CONCORRENTE"),
        ("o relatório dá erro toda vez que exporto", "RECLAMACAO_PRODUTO"),
        ("não acessam a plataforma há oito meses", "INATIVIDADE_PROLONGADA"),
    ])
    def test_each_catalogue_code_has_a_working_trigger(self, sentence, expected):
        assert expected in churn_motives(sentence)

    def test_cancellation_threat_outweighs_a_complaint(self):
        threat = calculate_churn_risk(churn_motives("vamos rescindir o contrato")).score
        complaint = calculate_churn_risk(churn_motives("o sistema trava sempre")).score
        assert threat > complaint

    def test_two_signals_add_up(self):
        text = ("estamos insatisfeitos com o serviço. "
                "recebemos uma proposta da concorrência.")
        assert calculate_churn_risk(churn_motives(text)).score == 55


class TestOpportunity:
    def test_currency_figure_counts_as_budget(self):
        assert "MENCAO_BUDGET" in opportunity_motives("pacotes de 15 20 mil mês")

    def test_bare_number_alone_is_not_budget(self):
        assert "MENCAO_BUDGET" not in opportunity_motives("temos 15 lojas em são paulo")

    def test_deadline_counts_even_inside_a_hypothetical(self):
        """Unlike churn, a stated figure or date is a fact regardless of framing."""
        assert "PRAZO_DEFINIDO" in opportunity_motives("se aprovarem, entregamos em 30 dias")

    def test_score_is_capped_at_one_hundred(self):
        text = ("orçamento de R$ 40 mil, entrega em 30 dias, querem fazer teste, "
                "ampliar para novas lojas, atendeu super bem")
        assert calculate_opportunity_score(opportunity_motives(text)).score == 100


class TestDeterminism:
    @pytest.mark.parametrize("transcript", PROSPECTING)
    def test_same_text_always_yields_the_same_score(self, transcript):
        runs = {calculate_opportunity_score(opportunity_motives(transcript)).score
                for _ in range(5)}
        assert len(runs) == 1

    def test_accents_and_case_do_not_change_the_outcome(self):
        assert churn_motives("VAMOS RESCINDIR O CONTRATO") == \
               churn_motives("vamos rescindir o contrato")
