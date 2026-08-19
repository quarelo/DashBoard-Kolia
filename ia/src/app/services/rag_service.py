from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.app.models.analysis import MeetingAnalysis, MeetingChunk
from src.app.services.llm_service import generate_embedding


class RagNotReadyError(RuntimeError):
    pass


# One embedding query is reused by related fields. This keeps semantic
# retrieval useful without paying for thirteen nearly identical Ollama calls.
_CATEGORY_QUERY_GROUPS = {
    "produto": "produtos TOTVS, módulos, sistemas e funcionalidades mencionados",
    "persona": "perfil e função profissional das pessoas participantes",
    "sentimento": "percepção, satisfação, elogios e reclamações do cliente",
    "risco_churn": "cancelamento, insatisfação, risco de perda e intenção de sair",
    "oportunidade_comercial": "venda, expansão, upsell, novos módulos e serviços",
    "score_oportunidade": "potencial, urgência e valor comercial da oportunidade",
    "budget": "preços, orçamento, investimento, licenças e valores financeiros",
    "gap_produto": "necessidades não atendidas, limitações e funcionalidades ausentes",
    "problemas_identificados": "dores, erros, obstáculos e dificuldades relatadas",
    "feedback_produto": "opiniões, avaliação e feedback sobre produtos usados",
    "evidencias": "trechos concretos que comprovam decisões, dores e necessidades",
    "recomendacao_acao": "próximos passos, tarefas, responsáveis e prazos combinados",
    "duvidas_em_aberto": "perguntas e dúvidas ainda sem resposta",
}
_CATEGORY_QUERY_CACHE = {
    "produto": "produto e persona",
    "persona": "produto e persona",
    "sentimento": "sentimento e churn",
    "risco_churn": "sentimento e churn",
    "oportunidade_comercial": "oportunidade e score comercial",
    "score_oportunidade": "oportunidade e score comercial",
    "budget": "budget e valores",
    "gap_produto": "gaps e problemas",
    "problemas_identificados": "gaps e problemas",
    "feedback_produto": "gaps e problemas",
    "evidencias": "evidências e ações",
    "recomendacao_acao": "evidências e ações",
    "duvidas_em_aberto": "evidências e ações",
}
_GROUP_QUERIES = {
    "produto e persona": "produtos TOTVS, módulos, sistemas e perfil profissional dos participantes",
    "sentimento e churn": "percepção, satisfação, reclamações, cancelamento e risco de perda",
    "oportunidade e score comercial": "venda, expansão, upsell, potencial e urgência comercial",
    "budget e valores": "preços, orçamento, investimento, licenças e valores financeiros",
    "gaps e problemas": "necessidades não atendidas, limitações, dores, erros e obstáculos",
    "evidências e ações": "trechos concretos, próximos passos, tarefas, prazos e dúvidas sem resposta",
}


def search_analysis_chunks(
    db: Session,
    analysis_id: UUID,
    query: str,
    top_k: int = 5,
) -> dict:
    analysis = db.get(MeetingAnalysis, analysis_id)
    if analysis is None:
        raise ValueError("Análise não encontrada.")

    missing = db.execute(
        select(func.count(MeetingChunk.id)).where(
            MeetingChunk.analysis_id == analysis_id,
            MeetingChunk.embedding.is_(None),
        )
    ).scalar_one()
    if analysis.status != "DONE" or missing:
        raise RagNotReadyError(
            "A busca semântica estará disponível quando todos os embeddings terminarem."
        )

    query_embedding = generate_embedding(query)
    distance = MeetingChunk.embedding.cosine_distance(query_embedding)
    statement = (
        select(MeetingChunk, distance.label("distance"))
        .where(
            MeetingChunk.analysis_id == analysis_id,
            MeetingChunk.embedding.is_not(None),
        )
        .order_by(distance.asc())
        .limit(top_k)
    )
    results = []
    for chunk, cosine_distance in db.execute(statement).all():
        similarity = max(0.0, min(1.0, 1.0 - float(cosine_distance)))
        content = chunk.clean_content or chunk.content
        results.append({
            "chunk_id": chunk.id,
            "chunk_index": chunk.chunk_index,
            "excerpt": content[:700],
            "similarity": round(similarity, 4),
        })
    return {
        "analysis_id": analysis_id,
        "query": query,
        "ready": True,
        "results": results,
    }


def search_analysis_categories(
    db: Session,
    analysis_id: UUID,
    top_k: int = 4,
) -> dict:
    """Retrieve semantically relevant chunks for all dashboard categories.

    Related categories share one query embedding, so this is seven embedding
    calls instead of one call per field. It returns evidence only; the final
    LLM remains responsible for interpreting the evidence and producing the
    13-field contract.
    """
    analysis = db.get(MeetingAnalysis, analysis_id)
    if analysis is None:
        raise ValueError("Análise não encontrada.")
    missing = db.execute(
        select(func.count(MeetingChunk.id)).where(
            MeetingChunk.analysis_id == analysis_id,
            MeetingChunk.embedding.is_(None),
        )
    ).scalar_one()
    if analysis.status != "DONE" or missing:
        raise RagNotReadyError(
            "A busca semântica estará disponível quando todos os embeddings terminarem."
        )

    top_k = max(1, min(int(top_k), 10))
    grouped_results: dict[str, list[dict]] = {}
    for group_name, query in _GROUP_QUERIES.items():
        query_embedding = generate_embedding(query)
        distance = MeetingChunk.embedding.cosine_distance(query_embedding)
        statement = (
            select(MeetingChunk, distance.label("distance"))
            .where(
                MeetingChunk.analysis_id == analysis_id,
                MeetingChunk.embedding.is_not(None),
            )
            .order_by(distance.asc())
            .limit(top_k)
        )
        rows = []
        for chunk, cosine_distance in db.execute(statement).all():
            content = chunk.clean_content or chunk.content
            rows.append({
                "chunk_id": chunk.id,
                "chunk_index": chunk.chunk_index,
                "excerpt": content[:700],
                "similarity": round(max(0.0, min(1.0, 1.0 - float(cosine_distance))), 4),
            })
        grouped_results[group_name] = rows

    categories = {
        category: grouped_results[_CATEGORY_QUERY_CACHE[category]]
        for category in _CATEGORY_QUERY_GROUPS
    }
    return {"analysis_id": analysis_id, "ready": True, "categories": categories}
