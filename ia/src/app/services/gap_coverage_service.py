"""Casa cada gap de produto contra o catálogo real da TOTVS (``ai.products``).

A pergunta que isto responde é "o cliente pediu algo que a TOTVS já vende?" —
sugestão de cross-sell quando sim, pauta de roadmap quando não. Reaproveita o
mesmo caminho de `product_service.find_candidate_products`: embeddar o texto e
ordenar o catálogo por distância de cosseno.

**O critério é a margem, não a distância absoluta.** Isto não é uma escolha de
estilo; foi medido nos 354 gaps distintos da carga atual contra os 302 produtos
do catálogo, e a distância ao vizinho mais próximo é comprimida demais para
discriminar: p5 = 0,233, mediana = 0,293, p90 = 0,339. Um texto de gap e uma
descrição de produto são os dois prosa comercial em português, então o cosseno
mede sobretudo isso, não a aderência de tema. Com um corte absoluto de 0,25
sobram 11% dos gaps, e na inspeção manual uns 35% deles estão errados
("Ausência de banco de talentos online" → *TOTVS Central do Cliente*).

A margem entre o 1º e o 5º vizinho (``d5 - d1``) separa bem: quando o catálogo
inteiro está equidistante do gap, não há match nenhum, e é exatamente isso que
margem baixa significa. Nos 12 gaps de maior margem a inspeção manual deu 12
acertos (chatbot → *Chat Commerce by Chatbot Maker*, PIX → *Recebe+ Conciliado
Techfin*, conciliação manual → *Conciliação Financeira by Boavista*); nos 8 de
menor margem, 8 rejeições corretas ("Falta de líder de produção definido na
empresa" → *Clima e Engajamento*, margem 0,006 — nem é gap de produto).

Daí as três faixas, e daí também o rótulo: "provável" e "possível", nunca
"coberto" — a resposta sempre devolve o nome e a distância para quem lê poder
descartar.

**A faixa do meio está desligada** (`gap_coverage_possible_enabled`) desde
2026-10-01, por acertar só cerca de metade: ela sugeriu *App Meu Controle
Fitossanitário* para um gap sobre visualizar carga e histórico de entrega num
CRM. O motivo não é o limiar — é que o vetor de cada produto inclui a descrição
de marketing inteira, e elas se parecem todas. Ver o comentário de
`gap_coverage_possible_enabled` em core/config.py.
"""
import logging
import time

from sqlalchemy import select, text as sql_text
from sqlalchemy.orm import Session

from src.app.core.config import settings
from src.app.models.product import Product
from src.app.services.llm_service import generate_embedding, generate_embeddings

logger = logging.getLogger("uvicorn.error")

COVERAGE_LIKELY = "provavel"
COVERAGE_POSSIBLE = "possivel"
COVERAGE_NONE = "sem_cobertura"

# Embeddar custa ~17 ms com o modelo residente, e o texto de um gap nunca muda
# depois que a análise fecha — então o mesmo gap reembeddado a cada abertura da
# página era puro desperdício. (O que custa caro é o modelo *não* estar
# residente: ~5 s de carga. Contra isso o cache não ajuda por si, porque seria
# a primeira chamada a pagar; quem ajuda é o `keep_alive` em
# `generate_embeddings` e o `warm_all_gaps` do startup, que põe o cache quente
# antes de alguém abrir a página.) Cache em processo,
# não em tabela: os 356 gaps distintos da carga atual ocupam ~2,6 MB de vetor
# (768 floats), desprezível ao lado dos 4 GB que o Ollama segura, e assim não
# precisa de migration nem entra na lista de `AI_ROWS_BY_ANALYSIS` do backend.
# Esvazia no restart; se isso incomodar, o passo seguinte é uma tabela
# endereçada por hash do texto, que não é ligada a análise e portanto não
# complica a exclusão de reunião.
_EMBEDDING_CACHE: dict[str, list[float]] = {}
_CACHE_MAX = 5000

# Lote do aquecimento. Medido com os 356 gaps distintos da carga: uma chamada
# só custou 1,73 s e lotes de 64 custaram 1,51 s — empate dentro do ruído, e o
# lote ganha por limitar o tamanho do corpo quando a base crescer.
_WARM_BATCH = 64


def _store(text: str, embedding: list[float]) -> list[float]:
    if len(_EMBEDDING_CACHE) >= _CACHE_MAX:
        _EMBEDDING_CACHE.clear()
    _EMBEDDING_CACHE[text] = embedding
    return embedding


def _cached_embedding(text: str) -> list[float]:
    hit = _EMBEDDING_CACHE.get(text)
    if hit is not None:
        return hit
    return _store(text, generate_embedding(text))


def _warm_cache(texts: list[str]) -> int:
    """Embedda de uma vez os textos que ainda não estão no cache.

    Sem isto o laço de `match_gaps` fazia uma chamada ao Ollama por gap, e o que
    pesa numa chamada de embedding é o ida-e-volta, não o cálculo: medido com 20
    gaps, 400 ms em 20 chamadas contra 147 ms numa só. Devolve quantos textos
    foram embeddados, que é o número que distingue a primeira abertura de um
    produto das seguintes.
    """
    missing = [text for text in texts if text not in _EMBEDDING_CACHE]
    if not missing:
        return 0
    for start in range(0, len(missing), _WARM_BATCH):
        batch = missing[start:start + _WARM_BATCH]
        for text, embedding in zip(batch, generate_embeddings(batch)):
            _store(text, embedding)
    return len(missing)


# Todo texto de gap que existe no banco, distinto e aparado, do mais recente
# para o mais antigo. É a consulta do aquecimento: ela não recorta por produto
# porque o serviço de IA não lê `core.meetings` e, de todo modo, aquecer só um
# produto deixaria o próximo a pagar a conta.
_ALL_GAPS_SQL = """
SELECT DISTINCT ON (gap) btrim(gap) AS gap, a.created_at
  FROM ai.meeting_analyses a
  CROSS JOIN LATERAL jsonb_array_elements_text(
      CASE WHEN jsonb_typeof(a.final_summary -> 'gap_produto') = 'array'
           THEN a.final_summary -> 'gap_produto' ELSE '[]'::jsonb END
  ) AS gap
 WHERE btrim(gap) <> ''
 ORDER BY gap, a.created_at DESC
 LIMIT :limite
"""


def warm_all_gaps(db: Session) -> int:
    """Embedda no cache todo gap do banco. Devolve quantos textos entraram.

    Isto existe por causa do que a primeira abertura da Página de Produto
    pagava. Medido nesta máquina, com o Ollama já de pé: segunda abertura
    0,29 s, primeira abertura com o cache vazio e o modelo residente 0,57 s, e
    primeira abertura logo depois de um `docker compose up` **2,36 s** — porque
    o serviço começa a responder ~3 s antes de o aquecimento do modelo
    terminar, então quem abre a página nessa janela espera a carga do modelo de
    qualquer jeito. Com o Ollama fora do ar na subida da IA, o aquecimento se
    perdia de vez e a conta era 2,65 s.

    Aquecer os gaps junto resolve para **todos** os produtos de uma vez, e não
    só para o primeiro que alguém abrir: os 356 gaps distintos da carga atual
    custam 1,7 s numa thread de startup, onde ninguém está esperando, contra
    ~0,05 s de cache quente por abertura depois disso.

    `LIMIT _CACHE_MAX` não é zelo: `_store` **esvazia o cache inteiro** quando
    enche, então um aquecimento maior que o cache acabaria jogando fora o que
    ele mesmo acabou de pôr. Se a base passar disso, o certo é subir o limite ou
    partir para a tabela endereçada por hash, não deixar o aquecimento girar.

    O log separa SQL de embedding porque os dois já divergiram muito: em três
    restarts seguidos o total ficou em 3,05 / 2,94 / 2,84 s, com o SQL em 0,09 s
    — mas o primeiro boot depois de um `--build` levou 16,05 s, com container
    frio, primeira conexão TLS no Postgres remoto e a recuperação do worker
    junto. Sem os dois números na mesma linha, a próxima vez que isso aparecer
    vira adivinhação.
    """
    sql_started = time.perf_counter()
    rows = db.execute(sql_text(_ALL_GAPS_SQL), {"limite": _CACHE_MAX}).all()
    gaps = [row.gap for row in rows]
    sql_seconds = time.perf_counter() - sql_started
    if not gaps:
        logger.info("gap_warmup_vazio sql=%.2fs", sql_seconds)
        return 0

    embed_started = time.perf_counter()
    warmed = _warm_cache(gaps)
    logger.info(
        "gap_warmup gaps=%d lotes=%d sql=%.2fs embed=%.2fs",
        warmed, _WARM_BATCH, sql_seconds, time.perf_counter() - embed_started,
    )
    return warmed


def cache_size() -> int:
    """Quantos textos o cache guarda — exposto para o endpoint poder dizer se a
    resposta saiu quente ou pagou embedding, que é a diferença entre 50ms e 9s."""
    return len(_EMBEDDING_CACHE)


def _classify(d1: float, d5: float) -> str:
    """A faixa de um gap, pela margem — ver o docstring do módulo."""
    # Margem grande com o vizinho longe mesmo assim não quer dizer nada: é um
    # gap que o catálogo todo ignora, e um deles por acaso ignora menos.
    if d1 > settings.gap_coverage_distance_ceiling:
        return COVERAGE_NONE
    margin = d5 - d1
    if margin >= settings.gap_coverage_likely_margin:
        return COVERAGE_LIKELY
    if settings.gap_coverage_possible_enabled and margin >= settings.gap_coverage_possible_margin:
        return COVERAGE_POSSIBLE
    return COVERAGE_NONE


def match_gaps(db: Session, gaps: list[str], *, suggestions: int = 2) -> dict:
    """Para cada gap, a faixa de cobertura e os produtos do catálogo sugeridos.

    `gaps` vem já filtrado pelo backend (as reuniões daquele produto, sob os
    filtros do dashboard), porque o recorte depende de `core.meetings`, que este
    serviço não lê. Texto repetido é embeddado uma vez só.
    """
    unique = list(dict.fromkeys(gap.strip() for gap in gaps if gap and gap.strip()))
    if not unique:
        return {"itens": [], "resumo": {COVERAGE_LIKELY: 0, COVERAGE_POSSIBLE: 0, COVERAGE_NONE: 0}}

    top_k = max(5, suggestions)
    itens: list[dict] = []
    resumo = {COVERAGE_LIKELY: 0, COVERAGE_POSSIBLE: 0, COVERAGE_NONE: 0}

    # Uma chamada ao Ollama para todos os gaps que faltam, antes do laço. Depois
    # disto `_ranked` acha tudo em cache e só faz a busca vetorial.
    cold = _warm_cache(unique)

    for gap in unique:
        candidates = _ranked(db, gap, top_k)
        if len(candidates) < top_k:
            # Catálogo pequeno demais para a margem significar algo — sem o 5º
            # vizinho não há com o que comparar o 1º.
            resumo[COVERAGE_NONE] += 1
            itens.append({"gap": gap, "cobertura": COVERAGE_NONE, "distancia": None, "produtos": []})
            continue
        d1 = candidates[0][1]
        d5 = candidates[top_k - 1][1]
        cobertura = _classify(d1, d5)
        resumo[cobertura] += 1
        itens.append({
            "gap": gap,
            "cobertura": cobertura,
            "distancia": round(d1, 4),
            "margem": round(d5 - d1, 4),
            # Só sugere produto quando há faixa; em "sem_cobertura" a lista vem
            # vazia de propósito, para a tela não exibir um palpite ruim ao lado
            # de um rótulo que diz justamente que não há match.
            "produtos": [] if cobertura == COVERAGE_NONE else [
                {"nome": product.name, "url": product.source_url, "distancia": round(distance, 4)}
                for product, distance in candidates[:suggestions]
            ],
        })

    logger.info(
        "gap_coverage gaps=%d embeddings_novos=%d cache=%d provavel=%d possivel=%d sem=%d",
        len(unique), cold, cache_size(),
        resumo[COVERAGE_LIKELY], resumo[COVERAGE_POSSIBLE], resumo[COVERAGE_NONE],
    )
    return {"itens": itens, "resumo": resumo}


def _ranked(db: Session, gap: str, top_k: int) -> list[tuple]:
    """Os `top_k` produtos mais próximos do gap, reusando o embedding em cache.

    `product_service.find_candidate_products` embedda por conta própria, o que é
    o certo para o caminho de grounding (uma chamada por análise) e errado aqui
    (uma por gap, repetida a cada abertura de página). A ordenação em si é a
    mesma consulta.
    """
    embedding = _cached_embedding(gap)
    distance = Product.embedding.cosine_distance(embedding)
    statement = select(Product, distance.label("distance")).order_by(distance.asc()).limit(top_k)
    return [(product, float(value)) for product, value in db.execute(statement).all()]


__all__ = [
    "COVERAGE_LIKELY", "COVERAGE_NONE", "COVERAGE_POSSIBLE", "cache_size", "match_gaps",
]
