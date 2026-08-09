from src.app.core.config import settings
from src.app.services.llm_service import (
    consolidate_mock_summaries,
    generate_fake_embedding,
    generate_mock_chunk_summary,
)


def test_generate_mock_chunk_summary_exposes_expected_business_sections():
    summary = generate_mock_chunk_summary("Cliente precisa integrar o ERP.")

    assert summary["temas_discutidos"] == ["Cliente precisa integrar o ERP."]
    assert summary["decisoes_tomadas"] == []
    assert summary["metricas_negocio"]["produtos_servicos_citados"] == []


def test_consolidate_mock_summaries_collects_chunk_topics():
    final_summary = consolidate_mock_summaries(
        [
            {"temas_discutidos": ["Integração"]},
            {"temas_discutidos": ["Prazo"]},
        ]
    )

    assert final_summary["temas_agrupados"][0]["pontos"] == ["Integração", "Prazo"]


def test_generate_fake_embedding_is_deterministic_and_has_configured_dimension():
    first = generate_fake_embedding("conteúdo")
    second = generate_fake_embedding("conteúdo")

    assert first == second
    assert len(first) == settings.embedding_dim
    assert abs(sum(value * value for value in first) - 1.0) < 1e-9
