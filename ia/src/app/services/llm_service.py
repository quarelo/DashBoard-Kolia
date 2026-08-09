import hashlib
import math

from src.app.core.config import settings


def _empty_metrics() -> dict:
    return {"valor_venda": "", "valor_contrato": "", "quantidade_usuarios": "", "quantidade_licencas": "", "prazo": "", "desconto": "", "produtos_servicos_citados": [], "valores_financeiros_citados": []}


def generate_mock_chunk_summary(clean_content: str) -> dict:
    preview = clean_content[:500]
    return {"temas_discutidos": [preview] if preview else [], "problemas_identificados": [], "decisoes_tomadas": [], "duvidas_em_aberto": [], "oportunidades_insights": [], "evidencias_importantes": [], "metricas_negocio": _empty_metrics()}


def consolidate_mock_summaries(chunk_summaries: list[dict]) -> dict:
    topics = []
    for summary in chunk_summaries:
        topics.extend(summary.get("temas_discutidos", []))
    return {"resumo_geral": "Resumo mockado gerado para validar o fluxo inicial da IA.", "temas_agrupados": [{"tema": "Conteúdo principal da reunião", "pontos": topics[:10]}], "problemas_identificados": [], "decisoes_tomadas": [], "duvidas_em_aberto": [], "oportunidades_insights": [], "evidencias_importantes": [], "metricas_negocio": _empty_metrics(), "acoes_recomendadas": []}


def generate_fake_embedding(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values = [(digest[index % len(digest)] / 255.0) - 0.5 for index in range(settings.embedding_dim)]
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]
