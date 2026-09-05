"""Tests for scoring_service module."""

import pytest

from src.app.services.scoring_service import (
    ChurnMotive,
    OpportunityMotive,
    calculate_churn_risk,
    calculate_opportunity_score,
    infer_churn_motives,
    infer_opportunity_motives,
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

        # Multiple motives: sum is 50 + 30 + 25 = 105, capped at 100
        assert calculate_churn_risk([
            ChurnMotive.AMEACA_CANCELAMENTO.value,
            ChurnMotive.INSATISFACAO_EXPLICITA.value,
            ChurnMotive.MENCAO_CONCORRENTE.value,
        ]).score == 100

    def test_score_capped_at_100(self):
        """Score must never exceed 100 even when sum of motives does."""
        # Sum: 50 + 30 + 25 + 15 = 120
        result = calculate_churn_risk([
            ChurnMotive.AMEACA_CANCELAMENTO.value,
            ChurnMotive.INSATISFACAO_EXPLICITA.value,
            ChurnMotive.MENCAO_CONCORRENTE.value,
            ChurnMotive.RECLAMACAO_PRODUTO.value,
        ])
        assert result.score == 100

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

        # Multiple motives: sum is 40 + 30 + 25 = 95
        assert calculate_opportunity_score([
            OpportunityMotive.PEDIDO_EXPANSAO.value,
            OpportunityMotive.MENCAO_BUDGET.value,
            OpportunityMotive.PRAZO_DEFINIDO.value,
        ]).score == 95

    def test_score_capped_at_100(self):
        """Score must never exceed 100 even when sum of motives does."""
        # Sum: 40 + 30 + 25 + 20 = 115
        result = calculate_opportunity_score([
            OpportunityMotive.PEDIDO_EXPANSAO.value,
            OpportunityMotive.MENCAO_BUDGET.value,
            OpportunityMotive.PRAZO_DEFINIDO.value,
            OpportunityMotive.INTERESSE_NOVO_MODULO.value,
        ])
        assert result.score == 100

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


class TestChurnMotiveInference:
    """Test heuristic inference of churn motives from text."""

    def test_infer_cancelation_threat(self):
        """Text mentioning contract cancellation should infer AMEACA_CANCELAMENTO."""
        test_cases = [
            "Cliente ameaçou cancelar o contrato",
            "Possibilidade de encerramento",
            "Ameaça de rescisão",
            "Vai cancelar se não houver melhoria",
        ]
        for text in test_cases:
            motives = infer_churn_motives(text)
            assert ChurnMotive.AMEACA_CANCELAMENTO.value in motives

    def test_infer_explicit_dissatisfaction(self):
        """Text with dissatisfaction keywords should infer INSATISFACAO_EXPLICITA."""
        test_cases = [
            "Cliente insatisfeito com o produto",
            "Muito descontente com o resultado",
            "Grande frustração com a solução",
        ]
        for text in test_cases:
            motives = infer_churn_motives(text)
            assert ChurnMotive.INSATISFACAO_EXPLICITA.value in motives

    def test_infer_competitor_mention(self):
        """Text mentioning alternatives should infer MENCAO_CONCORRENTE."""
        test_cases = [
            "Estão analisando a concorrência",
            "Existe outra solução mais barata",
            "Pensando em trocar de fornecedor",
        ]
        for text in test_cases:
            motives = infer_churn_motives(text)
            assert ChurnMotive.MENCAO_CONCORRENTE.value in motives

    def test_infer_product_complaint(self):
        """Text with product issues should infer RECLAMACAO_PRODUTO."""
        test_cases = [
            "Sistema muito lento",
            "Muitos erros no cadastro",
            "Falhas frequentes",
        ]
        for text in test_cases:
            motives = infer_churn_motives(text)
            assert ChurnMotive.RECLAMACAO_PRODUTO.value in motives

    def test_infer_inactivity_prolonged(self):
        """Text about potential loss should infer INATIVIDADE_PROLONGADA."""
        # These are the real cases from production that failed before
        test_cases = [
            "Potencial de perda se os clientes não encontrarem valor",
            "Potencial de não seguir com a proposta",
            "Risco de não retornar se não ver resultado",
            "Cliente pode deixar de usar o sistema",
        ]
        for text in test_cases:
            motives = infer_churn_motives(text)
            # At least INATIVIDADE_PROLONGADA should be identified
            assert ChurnMotive.INATIVIDADE_PROLONGADA.value in motives

    def test_infer_no_churn_motive(self):
        """Text without churn signals should return empty list."""
        text = "Cliente satisfeito com a apresentação"
        motives = infer_churn_motives(text)
        assert motives == []


class TestOpportunityMotiveInference:
    """Test heuristic inference of opportunity motives from text."""

    def test_infer_expansion_request(self):
        """Text about growth should infer PEDIDO_EXPANSAO."""
        test_cases = [
            "Quer expandir para novos usuários",
            "Plano de crescimento com mais licenças",
            "Adicionar mais módulos",
        ]
        for text in test_cases:
            motives = infer_opportunity_motives(text)
            assert OpportunityMotive.PEDIDO_EXPANSAO.value in motives

    def test_infer_budget_mention(self):
        """Text mentioning money should infer MENCAO_BUDGET."""
        test_cases = [
            "R$ 50 mil de investimento",
            "Orçamento de 2 milhões",
            "Custo unitário de R$ 100",
        ]
        for text in test_cases:
            motives = infer_opportunity_motives(text)
            assert OpportunityMotive.MENCAO_BUDGET.value in motives

    def test_infer_timeline_defined(self):
        """Text with dates/times should infer PRAZO_DEFINIDO."""
        test_cases = [
            "Implementar na segunda-feira",
            "Até o final de junho",
            "Próximo trimestre",
            "Hoje mesmo começamos",
        ]
        for text in test_cases:
            motives = infer_opportunity_motives(text)
            assert OpportunityMotive.PRAZO_DEFINIDO.value in motives

    def test_infer_new_module_interest(self):
        """Text about new features should infer INTERESSE_NOVO_MODULO."""
        test_cases = [
            "Interessados no novo módulo de CRM",
            "Precisa de integração com API",
            "Upgrade para a versão premium",
        ]
        for text in test_cases:
            motives = infer_opportunity_motives(text)
            assert OpportunityMotive.INTERESSE_NOVO_MODULO.value in motives

    def test_infer_customer_praise(self):
        """Text with positive feedback should infer ELOGIO_CLIENTE."""
        test_cases = [
            "Adorou a apresentação",
            "Excelente solução",
            "Muito satisfeito com o resultado",
        ]
        for text in test_cases:
            motives = infer_opportunity_motives(text)
            assert OpportunityMotive.ELOGIO_CLIENTE.value in motives

    def test_infer_no_opportunity_motive(self):
        """Text without opportunity signals should return empty list."""
        text = "Cliente apenas fez perguntas técnicas"
        motives = infer_opportunity_motives(text)
        assert motives == []


class TestRealWorldCases:
    """Test actual cases that failed in production."""

    def test_potential_loss_now_scores_above_zero(self):
        """
        Production case: "Potencial de perda se os clientes não encontrarem valor"
        should now be identified and produce score > 0.
        """
        text = "Potencial de perda se os clientes não encontrarem valor"
        motives = infer_churn_motives(text)
        result = calculate_churn_risk(motives)

        # Should identify at least inactivity prolonged (10 points)
        assert result.score > 0
        assert ChurnMotive.INATIVIDADE_PROLONGADA.value in result.motives

    def test_no_follow_up_now_scores_above_zero(self):
        """
        Production case: "Potencial de não seguir com a proposta"
        should now be identified and produce score > 0.
        """
        text = "Potencial de não seguir com a proposta"
        motives = infer_churn_motives(text)
        result = calculate_churn_risk(motives)

        # Should identify at least inactivity prolonged (10 points)
        assert result.score > 0
        assert ChurnMotive.INATIVIDADE_PROLONGADA.value in result.motives

    def test_explicit_threat_still_works(self):
        """Explicit threats like before should continue to work."""
        text = "Cliente ameaçou cancelar o contrato"
        motives = infer_churn_motives(text)
        result = calculate_churn_risk(motives)

        assert result.score == 50
        assert ChurnMotive.AMEACA_CANCELAMENTO.value in result.motives


class TestDeclaredCodesWinOverWording:
    """The point of the enum: scoring must not depend on how the model phrased a fact.

    In production 250 of 500 churn signals scored 0 because the wording
    ("Potencial de perda...") missed a regex vocabulary. A declared code carries
    the classification, so the same meaning scores the same regardless of wording.
    """

    def test_declared_code_scores_even_when_wording_matches_nothing(self):
        from src.app.services.analysis_service import build_compact_final_summary

        summary = {
            "pontos_chave": ["CHURN: cliente pode não fechar, vamos ver depois"],
            "motivos_churn": ["AMEACA_CANCELAMENTO"],
            "motivos_oportunidade": [],
        }
        result = build_compact_final_summary([summary], ["texto de origem"])
        assert result["risco_churn"]["score"] == 50

    def test_two_different_wordings_of_one_code_score_the_same(self):
        from src.app.services.analysis_service import build_compact_final_summary

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
