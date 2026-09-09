import re
import unicodedata
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.app.models.analysis import ChunkPassage, MeetingAnalysis, MeetingChunk
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
    # The query side keeps the framing words here, unlike `_lexical_query`.
    # Removing them was tried and measured worse: the overlap that drives this
    # rerank got so thin that "Quais produtos foram mencionados?" stopped
    # selecting the passages about products at all (chunks 15 and 9 gave way to 7
    # and 9, and the passage that lists product groups fell out of both). A weak
    # signal with some noise beat a cleaner signal with almost nothing in it.
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


# Fusion constant: with k=60 the top of each list dominates without a single
# method being able to shut the other out. It is the value the RRF paper uses and
# the one every implementation defaults to; nothing here depends on it being exact.
RRF_K = 60
# A term in more than this share of an analysis's passages does not tell the
# search which one answers; below this many passages the share is meaningless.
_MAX_TERM_SHARE = 0.35
_MIN_PASSAGES_FOR_IDF = 12


def _lexical_query(db: Session, analysis_id: UUID, query: str) -> str:
    """OR of the query terms that actually discriminate, judged by this analysis.

    OR because a question is not a phrase to match: `plainto_tsquery` ANDs the
    terms, and "prazo data sexta entrega" then matched nothing at all.

    Discriminating, because OR alone is worse than useless: "O que falaram sobre
    boleto?" became `boleto | sobre | falaram`, which matched 79 passages, and
    ts_rank ranks by term frequency — the two passages that really discuss boleto
    sank under passages repeating "falaram". Terms carried by most of the corpus
    say nothing about which passage answers.

    The cut is measured against the analysis being searched, not a written list of
    stop words: a word that is generic here may be the whole point elsewhere, and
    a hand-kept vocabulary is exactly what this search is meant to avoid.

    Framing words survive it — "gostaria de saber sobre quais produtos estão sendo
    falados na reunião" keeps `gostaria | quai | sobre | produto | sendo | saber`,
    since a word the asker supplied is rare in the meeting precisely because the
    meeting is not about it. Two ways of removing them were measured and both were
    worse, so the noise stays:

    - A list of Portuguese framing words, cutting the query to `produto`, lost a
      question that the noisy query had answered and dropped the passage listing
      product groups out of "Quais produtos foram mencionados?" — 6 of 8 answered
      against 7 of 8, with two refusals against one. One surviving term leaves
      ts_rank nothing to order by; the noise was carrying some signal.
    - Keeping only terms found in the semantically nearest passages cut nothing
      here (framing words appear in any transcribed speech) and emptied the query
      for "Quantas máquinas precisam ser substituídas?".
    """
    terms = [t for t in _excerpt_terms(query) if len(t) > 2]
    if not terms:
        return ""
    total = db.execute(
        select(func.count(ChunkPassage.id))
        .where(ChunkPassage.analysis_id == analysis_id)
    ).scalar_one() or 0
    if total < _MIN_PASSAGES_FOR_IDF:
        return " | ".join(terms)

    discriminating = []
    for term in terms:
        matches = db.execute(
            select(func.count(ChunkPassage.id)).where(
                ChunkPassage.analysis_id == analysis_id,
                ChunkPassage.search_vector.op("@@")(
                    func.to_tsquery("portuguese", term)),
            )
        ).scalar_one()
        if matches and matches <= total * _MAX_TERM_SHARE:
            discriminating.append(term)
    # Everything the person asked is common here; better a broad match than none.
    return " | ".join(discriminating or terms)


def _fuse(vector_ids: list, lexical_ids: list) -> dict:
    """Reciprocal rank fusion: score each id by its position in each list.

    The two methods fail differently — vector search finds the topic and loses the
    specific fact, lexical search finds the word and loses the context — so a
    passage ranked well by either one deserves to be considered. Fusing by rank
    rather than by score avoids comparing a cosine distance to a ts_rank, which
    are not on the same scale and never will be.
    """
    scores: dict = {}
    for ranking in (vector_ids, lexical_ids):
        for position, identifier in enumerate(ranking, start=1):
            scores[identifier] = scores.get(identifier, 0.0) + 1.0 / (RRF_K + position)
    return scores


def _passage_search(db: Session, analysis_id: UUID, query: str,
                    query_embedding: list, top_k: int) -> list:
    """Candidates from both methods, merged by rank."""
    distance = ChunkPassage.embedding.cosine_distance(query_embedding)
    # Deeper than top_k on each side: fusion only helps if it has something to
    # merge, and the passage that answers is often mid-list on one of them.
    depth = max(top_k * 4, 20)
    vector_rows = db.execute(
        select(ChunkPassage, MeetingChunk.chunk_index, distance.label("distance"))
        .join(MeetingChunk, MeetingChunk.id == ChunkPassage.chunk_id)
        .where(ChunkPassage.analysis_id == analysis_id,
               ChunkPassage.embedding.is_not(None))
        .order_by(distance.asc()).limit(depth)
    ).all()

    lexical_rows = []
    tsquery = _lexical_query(db, analysis_id, query)
    if tsquery:
        rank = func.ts_rank(ChunkPassage.search_vector,
                            func.to_tsquery("portuguese", tsquery))
        lexical_rows = db.execute(
            select(ChunkPassage, MeetingChunk.chunk_index, rank.label("rank"))
            .join(MeetingChunk, MeetingChunk.id == ChunkPassage.chunk_id)
            .where(ChunkPassage.analysis_id == analysis_id,
                   ChunkPassage.search_vector.op("@@")(
                       func.to_tsquery("portuguese", tsquery)))
            .order_by(rank.desc()).limit(depth)
        ).all()

    by_id = {}
    similarity = {}
    for passage, chunk_index, cosine_distance in vector_rows:
        by_id[passage.id] = (passage, chunk_index)
        similarity[passage.id] = max(0.0, min(1.0, 1.0 - float(cosine_distance)))
    for passage, chunk_index, _rank in lexical_rows:
        by_id.setdefault(passage.id, (passage, chunk_index))

    scores = _fuse([p.id for p, _c, _d in vector_rows],
                   [p.id for p, _c, _r in lexical_rows])
    ordered = sorted(scores, key=lambda pid: scores[pid], reverse=True)[:top_k]
    return [(by_id[pid][0], by_id[pid][1], similarity.get(pid, 0.0)) for pid in ordered]


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

    # A chunk is searchable through its passages or, for analyses indexed before
    # passages existed, through its own vector. Requiring the chunk vector as well
    # would force it to be computed for every new chunk just to satisfy this
    # check, and nothing would ever read it — the passage path returns first.
    indexed_passage = (
        select(ChunkPassage.id)
        .where(ChunkPassage.chunk_id == MeetingChunk.id,
               ChunkPassage.embedding.is_not(None))
        .exists()
    )
    missing = db.execute(
        select(func.count(MeetingChunk.id)).where(
            MeetingChunk.analysis_id == analysis_id,
            MeetingChunk.embedding.is_(None),
            ~indexed_passage,
        )
    ).scalar_one()
    if analysis.status != "DONE" or missing:
        raise RagNotReadyError(
            "A busca semântica estará disponível quando todos os embeddings terminarem."
        )

    query_embedding = generate_embedding(query)
    results = []

    # Passages first: a vector over ~400 tokens can point at the sentence that
    # names a price, where one vector averaged over a whole 2000-token chunk
    # cannot — asking about values used to return five chunks above the threshold
    # and none of the four that mention R$.
    for passage, chunk_index, similarity in _passage_search(
            db, analysis_id, query, query_embedding, top_k):
        results.append({
            "chunk_id": passage.chunk_id,
            "chunk_index": chunk_index,
            "excerpt": extract_relevant_excerpt(passage.content, query, excerpt_chars),
            "similarity": round(similarity, 4),
        })

    if results:
        return {"analysis_id": analysis_id, "query": query, "ready": True,
                "results": results}

    # Analyses indexed before passages existed still answer from chunk vectors.
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
