import re
import unicodedata
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.app.models.analysis import MeetingAnalysis, MeetingChunk
from src.app.services.llm_service import generate_embedding


class RagNotReadyError(RuntimeError):
    pass


_EXCERPT_STOPWORDS = {
    "a", "ao", "aos", "as", "com", "como", "da", "das", "de", "do",
    "dos", "e", "em", "essa", "esse", "esta", "este", "ficou", "na", "nas",
    "no", "nos", "o", "os", "ou", "para", "pela", "pelo", "por", "qual",
    "que", "se", "um", "uma", "era",
}


def _excerpt_terms(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKD", text.lower())
    normalized = "".join(
        character for character in normalized
        if not unicodedata.combining(character)
    )
    terms = set()
    for token in re.findall(r"[a-z0-9]+", normalized):
        if len(token) < 3 or token in _EXCERPT_STOPWORDS:
            continue
        singular = token[:-1] if token.endswith("s") and len(token) > 4 else token
        if singular.startswith("substitu"):
            singular = "substitu"
        elif singular.startswith("revis"):
            singular = "revis"
        elif singular.startswith("estim"):
            singular = "estim"
        terms.add(singular)
    return terms


def excerpt_relevance_score(content: str, query: str) -> int:
    query_terms = _excerpt_terms(query)
    content_terms = _excerpt_terms(content)
    overlap = len(query_terms & content_terms)
    normalized_content = unicodedata.normalize("NFKD", content.lower())
    normalized_content = "".join(
        character for character in normalized_content
        if not unicodedata.combining(character)
    )
    normalized_content = re.sub(
        r"\[\s*(?:l|locutor)\s*\d+\s*\]\s*: ?",
        " ",
        normalized_content,
    )
    normalized_query = unicodedata.normalize("NFKD", " ".join(query.lower().split()))
    normalized_query = "".join(
        character for character in normalized_query
        if not unicodedata.combining(character)
    )
    asks_quantity = bool(re.search(
        r"\b(quant[oa]s?|quanto|estimativa|número|numero|valor|licenças?|licencas?)\b",
        normalized_query,
    ))
    close_number_and_term = False
    if asks_quantity:
        unit_match = re.search(
            r"\bquant(?:as|os|a|o)\s+([a-z0-9]+)", normalized_query
        )
        proximity_terms = (
            _excerpt_terms(unit_match.group(1)) if unit_match else query_terms
        )
        for term in proximity_terms:
            if len(term) < 4:
                continue
            escaped = re.escape(term)
            if re.search(
                rf"(?:\d[\d.,]*.{{0,15}}\b{escaped}\w*|"
                rf"\b{escaped}\w*.{{0,15}}\d)",
                normalized_content,
                re.DOTALL,
            ):
                close_number_and_term = True
                break
    quantity_bonus = 25 if close_number_and_term else (
        2 if asks_quantity and re.search(r"\d", normalized_content) else 0
    )
    asks_temporal = bool(re.search(
        r"\b(quando|mes|meses|prazo|data|dia)\b", normalized_query
    ))
    temporal_value = bool(re.search(
        r"\b(janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|"
        r"setembro|outubro|novembro|dezembro|segunda(?:-feira)?|"
        r"terca(?:-feira)?|quarta(?:-feira)?|quinta(?:-feira)?|"
        r"sexta(?:-feira)?|sabado|domingo|\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b",
        normalized_content,
    ))
    temporal_bonus = 25 if asks_temporal and temporal_value else 0
    return overlap * 10 + quantity_bonus + temporal_bonus


def extract_relevant_excerpt(content: str, query: str, max_chars: int) -> str:
    max_chars = max(1, min(int(max_chars), 2000))
    if len(content) <= max_chars:
        return content

    step = max(100, max_chars // 3)
    starts = list(range(0, len(content) - max_chars + 1, step))
    starts.append(len(content) - max_chars)

    best_start = 0
    best_score = float("-inf")
    for start in starts:
        window = content[start:start + max_chars]
        score = excerpt_relevance_score(window, query)
        if score > best_score:
            best_start = start
            best_score = score

    if best_start:
        next_space = content.find(" ", best_start)
        if 0 <= next_space - best_start <= 40:
            best_start = next_space + 1
    return content[best_start:best_start + max_chars]


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
    excerpt_chars: int = 700,
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
            "excerpt": extract_relevant_excerpt(content, query, excerpt_chars),
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
