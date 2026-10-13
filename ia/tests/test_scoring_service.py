"""Tests for scoring_service module."""

import pytest

from src.app.services.scoring_service import (
    ChurnMotive,
    OpportunityMotive,
    Ruler,
    calculate_churn_risk,
    calculate_opportunity_score,
)


class TestChurnRiskDeterminism:
    """Determinism and consistency tests for churn risk calculation."""

    def test_same_motives_always_produce_same_score(self):
        """Same combination of motives must always produce identical score."""
        motives = [
            ChurnMotive.AMEACA_CANCELAMENTO.value,
            ChurnMotive.INSATISFACAO_EXPLICITA.value,
        ]

        result1 = calculate_churn_risk(motives)
        result2 = calculate_churn_risk(motives)

        assert result1.score == result2.score == 80  # 50 + 30
        assert result1.motives == result2.motives

    def test_correct_point_sum(self):
        """Scores must sum correctly from motive point values."""
        # Single motive tests
        assert calculate_churn_risk([ChurnMotive.AMEACA_CANCELAMENTO.value]).score == 50
        assert calculate_churn_risk([ChurnMotive.INSATISFACAO_EXPLICITA.value]).score == 30
        assert calculate_churn_risk([ChurnMotive.MENCAO_CONCORRENTE.value]).score == 25
        assert calculate_churn_risk([ChurnMotive.RECLAMACAO_PRODUTO.value]).score == 15
        assert calculate_churn_risk([ChurnMotive.INATIVIDADE_PROLONGADA.value]).score == 10

        # From the third code on the weight is discounted, so three codes are
        # 50 + 30 + 25/2 = 92.5, not the 105 that used to be capped at 100.
        assert calculate_churn_risk([
            ChurnMotive.AMEACA_CANCELAMENTO.value,
            ChurnMotive.INSATISFACAO_EXPLICITA.value,
            ChurnMotive.MENCAO_CONCORRENTE.value,
        ]).score == 93

    def test_the_whole_catalogue_no_longer_reaches_the_ceiling(self):
        """Listing every code was the cheapest way to score 100, and it should not be.

        All five churn codes used to sum to 130 and cap at 100; with the discount
        they reach 98, and the ceiling now needs weights that justify it.
        """
        result = calculate_churn_risk([motive.value for motive in ChurnMotive])
        assert result.score == 98

    def test_score_capped_at_100(self):
        """Score must never exceed 100, whatever weights the ruler carries."""
        heavy = Ruler(version=7, points={
            ChurnMotive.AMEACA_CANCELAMENTO.value: 90,
            ChurnMotive.INSATISFACAO_EXPLICITA.value: 80,
        })
        result = calculate_churn_risk(
            [ChurnMotive.AMEACA_CANCELAMENTO.value,
             ChurnMotive.INSATISFACAO_EXPLICITA.value],
            weights=heavy,
        )
        assert result.score == 100
        assert result.ruler_version == 7

    def test_duplicate_motives_count_once(self):
        """Same motive listed multiple times should count only once."""
        motives = [
            ChurnMotive.AMEACA_CANCELAMENTO.value,
            ChurnMotive.AMEACA_CANCELAMENTO.value,
            ChurnMotive.AMEACA_CANCELAMENTO.value,
        ]
        result = calculate_churn_risk(motives)

        # Should be 50, not 150
        assert result.score == 50
        assert result.motives == [ChurnMotive.AMEACA_CANCELAMENTO.value]

    def test_empty_motives_yields_zero_score(self):
        """Empty motive list must produce score 0."""
        result = calculate_churn_risk([])

        assert result.score == 0
        assert result.motives == []

    def test_unknown_motives_ignored_without_error(self):
        """Unknown motive codes must be ignored, not raise errors."""
        result = calculate_churn_risk([
            "UNKNOWN_MOTIVE",
            "INVALID_CODE",
            ChurnMotive.AMEACA_CANCELAMENTO.value,
        ])

        # Should work as if only valid motive was provided
        assert result.score == 50
        assert result.motives == [ChurnMotive.AMEACA_CANCELAMENTO.value]

    def test_mixed_valid_and_invalid_motives(self):
        """Mix of valid and invalid codes should process only valid ones."""
        result = calculate_churn_risk([
            ChurnMotive.AMEACA_CANCELAMENTO.value,
            "GARBAGE",
            ChurnMotive.INSATISFACAO_EXPLICITA.value,
            "INVALID",
        ])

        assert result.score == 80  # 50 + 30
        assert len(result.motives) == 2


class TestOpportunityScoringDeterminism:
    """Determinism and consistency tests for opportunity score calculation."""

    def test_same_motives_always_produce_same_score(self):
        """Same combination of motives must always produce identical score."""
        motives = [
            OpportunityMotive.PEDIDO_EXPANSAO.value,
            OpportunityMotive.MENCAO_BUDGET.value,
        ]

        result1 = calculate_opportunity_score(motives)
        result2 = calculate_opportunity_score(motives)

        assert result1.score == result2.score == 70  # 40 + 30
        assert result1.motives == result2.motives

    def test_correct_point_sum(self):
        """Scores must sum correctly from motive point values."""
        # Single motive tests
        assert calculate_opportunity_score([OpportunityMotive.PEDIDO_EXPANSAO.value]).score == 40
        assert calculate_opportunity_score([OpportunityMotive.MENCAO_BUDGET.value]).score == 30
        assert calculate_opportunity_score([OpportunityMotive.PRAZO_DEFINIDO.value]).score == 25
        assert calculate_opportunity_score([OpportunityMotive.INTERESSE_NOVO_MODULO.value]).score == 20
        assert calculate_opportunity_score([OpportunityMotive.ELOGIO_CLIENTE.value]).score == 15

        # Third code at half: 40 + 30 + 25/2 = 82.5.
        assert calculate_opportunity_score([
            OpportunityMotive.PEDIDO_EXPANSAO.value,
            OpportunityMotive.MENCAO_BUDGET.value,
            OpportunityMotive.PRAZO_DEFINIDO.value,
        ]).score == 83

    def test_four_codes_no_longer_land_on_the_ceiling(self):
        """The commonest four used to sum to 115 and cap at 100.

        42 of 198 analyses sat at exactly 100 because of this, which is what made
        the number useless for ranking.
        """
        result = calculate_opportunity_score([
            OpportunityMotive.PEDIDO_EXPANSAO.value,
            OpportunityMotive.MENCAO_BUDGET.value,
            OpportunityMotive.PRAZO_DEFINIDO.value,
            OpportunityMotive.INTERESSE_NOVO_MODULO.value,
        ])
        assert result.score == 88

    def test_duplicate_motives_count_once(self):
        """Same motive listed multiple times should count only once."""
        motives = [
            OpportunityMotive.ELOGIO_CLIENTE.value,
            OpportunityMotive.ELOGIO_CLIENTE.value,
        ]
        result = calculate_opportunity_score(motives)

        # Should be 15, not 30
        assert result.score == 15
        assert result.motives == [OpportunityMotive.ELOGIO_CLIENTE.value]

    def test_empty_motives_yields_zero_score(self):
        """Empty motive list must produce score 0."""
        result = calculate_opportunity_score([])

        assert result.score == 0
        assert result.motives == []

    def test_unknown_motives_ignored_without_error(self):
        """Unknown motive codes must be ignored, not raise errors."""
        result = calculate_opportunity_score([
            "UNKNOWN_MOTIVE",
            OpportunityMotive.PEDIDO_EXPANSAO.value,
            "INVALID",
        ])

        # Should work as if only valid motive was provided
        assert result.score == 40
        assert result.motives == [OpportunityMotive.PEDIDO_EXPANSAO.value]


class TestDeclaredCodesWinOverWording:
    """With a model that can classify, codes outrank wording.

    On in production since the move to qwen3.5:4b-q4_K_M; these still pin it on
    so the mechanism is exercised whatever the environment says.

    In production 250 of 500 churn signals scored 0 because the wording
    ("Potencial de perda...") missed a regex vocabulary. A declared code carries
    the classification, so the same meaning scores the same regardless of wording.
    """

    def test_declared_code_scores_even_when_wording_matches_nothing(self, monkeypatch):
        from src.app.core.config import settings
        from src.app.services.analysis_service import build_compact_final_summary

        monkeypatch.setattr(settings, "trust_declared_motives", True)

        summary = {
            "pontos_chave": ["CHURN: cliente pode não fechar, vamos ver depois"],
            "motivos_churn": ["AMEACA_CANCELAMENTO"],
            "motivos_oportunidade": [],
        }
        result = build_compact_final_summary([summary], ["texto de origem"])
        assert result["risco_churn"]["score"] == 50

    def test_two_different_wordings_of_one_code_score_the_same(self, monkeypatch):
        from src.app.core.config import settings
        from src.app.services.analysis_service import build_compact_final_summary

        monkeypatch.setattr(settings, "trust_declared_motives", True)

        scores = []
        for wording in ("Potencial de perda se os clientes não encontrarem valor",
                        "cliente sinalizou que talvez não continue"):
            result = build_compact_final_summary(
                [{"pontos_chave": [f"CHURN: {wording}"],
                  "motivos_churn": ["INSATISFACAO_EXPLICITA"],
                  "motivos_oportunidade": []}], ["origem"])
            scores.append(result["risco_churn"]["score"])
        assert scores[0] == scores[1] == 30

    def test_absent_codes_fall_back_to_text_inference(self):
        """Summaries written before the schema carried motives must still score."""
        from src.app.services.analysis_service import build_compact_final_summary

        legacy = {"pontos_chave": ["CHURN: cliente ameaçou cancelar o contrato"]}
        result = build_compact_final_summary([legacy], ["origem"])
        assert result["risco_churn"]["score"] > 0

    def test_invalid_declared_code_does_not_break_scoring(self):
        from src.app.services.analysis_service import build_compact_final_summary

        summary = {"pontos_chave": ["CHURN: algo"],
                   "motivos_churn": ["CODIGO_QUE_NAO_EXISTE"],
                   "motivos_oportunidade": []}
        result = build_compact_final_summary([summary], ["origem"])
        assert result["risco_churn"]["score"] == 0


class TestEnumeratedCodesNeverScore:
    """A model given room enumerates the catalogue instead of choosing.

    On the reference meeting a 1B declared all five churn codes and all five
    opportunity codes, turning a CRM demo into churn 100 where the rules said 30.
    That is why `trust_declared_motives` was off entirely.

    It is on now, for a model that does classify, so the protection moved into
    the scoring itself: a declaration covering the whole catalogue is dropped
    and the rules decide. Pinned on rather than left ambient, because the
    invariant has to hold in the configuration that actually trusts the model.
    """

    def test_enumerated_codes_do_not_override_the_rules(self, monkeypatch):
        from src.app.core.config import settings
        from src.app.services.analysis_service import build_compact_final_summary

        monkeypatch.setattr(settings, "trust_declared_motives", True)

        todos = ["AMEACA_CANCELAMENTO", "INSATISFACAO_EXPLICITA",
                 "MENCAO_CONCORRENTE", "RECLAMACAO_PRODUTO", "INATIVIDADE_PROLONGADA"]
        summary = {"pontos_chave": ["CHURN: necessidade de otimizar a troca"],
                   "motivos_churn": todos, "motivos_oportunidade": []}

        result = build_compact_final_summary([summary], ["demonstração de CRM"])

        assert result["risco_churn"]["score"] == 0, "sem sinal real, não pontua"

    def test_four_declared_codes_still_score(self, monkeypatch):
        """The guard has to stop enumeration without swallowing a real reading.

        Measured: on a transcript asking to expand to new stores with R$ 180 mil
        approved and a close by next month, the model declared these four, and
        all four were in the text.
        """
        from src.app.core.config import settings
        from src.app.services.analysis_service import build_compact_final_summary

        monkeypatch.setattr(settings, "trust_declared_motives", True)

        summary = {
            "pontos_chave": ["OPORTUNIDADE: querem ampliar para as novas lojas"],
            "motivos_churn": [],
            "motivos_oportunidade": [
                "PEDIDO_EXPANSAO", "MENCAO_BUDGET", "PRAZO_DEFINIDO",
                "INTERESSE_NOVO_MODULO",
            ],
        }

        result = build_compact_final_summary([summary], ["origem"])

        # 40 + 30 + 25/2 + 20/4 = 87.5, the four codes read without the ceiling.
        assert result["score_oportunidade"]["score"] == 88

    def test_a_score_and_its_reason_never_contradict(self):
        from src.app.services.analysis_service import build_compact_final_summary

        for pontos in (["CHURN: cliente ameaçou cancelar o contrato"],
                       ["OPORTUNIDADE: querem ampliar para novas lojas"],
                       ["PRODUTO: TOTVS ERP"]):
            result = build_compact_final_summary(
                [{"pontos_chave": pontos}], ["origem"])
            for campo, vazio in (("risco_churn", "Nenhum sinal"),
                                 ("score_oportunidade", "Nenhuma oportunidade")):
                bloco = result[campo]
                if bloco["score"]:
                    assert not bloco["justificativa"].startswith(vazio), \
                        f"{campo}: pontuou mas diz que não achou nada"
                else:
                    assert bloco["justificativa"].startswith(vazio), \
                        f"{campo}: não pontuou mas apresenta justificativa"


class TestEvidenceWeight:
    """Um código tem que valer pelo que sustenta, não por aparecer.

    Medido em 2026-10-09: a oportunidade mediana era 20 com um chunk e 90 a partir
    do terceiro, porque os códigos são unidos entre os chunks e uma menção única
    numa reunião longa pesava igual à reunião inteira falando do assunto.
    """

    def test_a_single_mention_in_a_long_meeting_counts_half(self):
        full = calculate_opportunity_score(
            [OpportunityMotive.PEDIDO_EXPANSAO.value],
            evidence={OpportunityMotive.PEDIDO_EXPANSAO.value: 0.5},
        ).score
        thin = calculate_opportunity_score(
            [OpportunityMotive.PEDIDO_EXPANSAO.value],
            evidence={OpportunityMotive.PEDIDO_EXPANSAO.value: 0.05},
        ).score
        assert full == 40
        assert thin == 20

    def test_a_quarter_of_the_chunks_is_already_full_weight(self):
        result = calculate_opportunity_score(
            [OpportunityMotive.PEDIDO_EXPANSAO.value],
            evidence={OpportunityMotive.PEDIDO_EXPANSAO.value: 0.25},
        )
        assert result.score == 40

    def test_the_score_does_not_grow_with_the_number_of_chunks(self):
        """O mesmo sinal, dito uma vez, não pode valer mais numa reunião longa."""
        from src.app.services.analysis_service import build_compact_final_summary

        declared = {"pontos_chave": ["OPORTUNIDADE: querem ampliar para novas lojas"],
                    "motivos_churn": [],
                    "motivos_oportunidade": [OpportunityMotive.PEDIDO_EXPANSAO.value]}
        quiet = {"pontos_chave": ["PRODUTO: TOTVS ERP"],
                 "motivos_churn": [], "motivos_oportunidade": []}

        short = build_compact_final_summary([declared])["score_oportunidade"]["score"]
        long = build_compact_final_summary(
            [declared] + [quiet] * 9)["score_oportunidade"]["score"]
        assert short >= long, "reunião longa não pode pontuar mais pelo tamanho"

    def test_a_quote_the_rules_confirm_counts_whole_however_long_the_meeting(self):
        """A citação literal é prova mais forte que a repetição.

        Senão o corte por frequência calaria sinal real: simulado, os zeros de
        churn subiam de 49 para 84.
        """
        from src.app.services.analysis_service import build_compact_final_summary

        threat = {"pontos_chave": ["CHURN: o cliente disse que vamos rescindir o contrato"],
                  "motivos_churn": [ChurnMotive.AMEACA_CANCELAMENTO.value],
                  "motivos_oportunidade": []}
        quiet = {"pontos_chave": ["PRODUTO: TOTVS ERP"],
                 "motivos_churn": [], "motivos_oportunidade": []}

        result = build_compact_final_summary([threat] + [quiet] * 19)
        assert result["risco_churn"]["score"] == 50


class TestRulerVersionTravelsWithTheScore:
    def test_the_score_records_which_ruler_measured_it(self):
        from src.app.services.analysis_service import build_compact_final_summary

        heavy = Ruler(version=9, points={ChurnMotive.AMEACA_CANCELAMENTO.value: 10})
        result = build_compact_final_summary(
            [{"pontos_chave": ["CHURN: cliente falou em rescindir o contrato"],
              "motivos_churn": [ChurnMotive.AMEACA_CANCELAMENTO.value],
              "motivos_oportunidade": []}],
            weights=heavy,
        )
        assert result["risco_churn"]["score"] == 10
        assert result["risco_churn"]["versao_regua"] == 9
        assert result["score_oportunidade"]["versao_regua"] == 9
