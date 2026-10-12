"""Ground `produto` against the real TOTVS catalogue instead of letting the
model name one from memory.

Distance decides the clear-cut cases; the model only arbitrates real
ambiguity, and only once per whole analysis, not per chunk. Full rationale
(why hybrid, why once per analysis, threshold values) in
docs/product-catalog-grounding.md — keep that doc in sync with this file.
"""
import logging
import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.app.core.config import settings
from src.app.models.product import Product
from src.app.services.llm_service import classify_products, generate_embedding
from src.app.services.transcript_aliases import normalize_aliases

logger = logging.getLogger("uvicorn.error")


def find_candidate_products(
    db: Session, text: str, top_k: int = 5
) -> list[tuple[Product, float]]:
    """The `top_k` catalogue entries closest to `text`, each with its cosine
    distance, ascending — index 0 is always the closest match.

    Same pattern already validated in scraper/search_sample.py and in
    rag_service's chunk search: embed the query, order ai.products by
    Product.embedding.cosine_distance, take the closest few.
    """
    embedding = generate_embedding(text)
    distance = Product.embedding.cosine_distance(embedding)
    statement = (
        select(Product, distance.label("distance"))
        .order_by(distance.asc())
        .limit(top_k)
    )
    return [(product, float(value)) for product, value in db.execute(statement).all()]


# Single words that name a product on their own and are not Portuguese words,
# so a bare mention counts ("o Fluig" means TOTVS Fluig; "analytics" means
# nothing in particular).
_BRAND_WORDS = frozenset({"fluig", "shopify", "varejonline"})


def _normalize(text: str) -> str:
    """Alias-fixed, lower-case, accent-free, words joined by single spaces."""
    text = unicodedata.normalize("NFKD", normalize_aliases(text).casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", text))


def _count(phrase: str, said: str) -> int:
    return len(re.findall(rf"\b{re.escape(phrase)}\b", said))


def catalogue_names(db: Session) -> list[str]:
    return list(db.scalars(select(Product.name)).all())


def find_literal_products(db: Session, transcript: str, top_k: int = 5) -> list[str]:
    """Catalogue names said literally in the transcript, most mentioned first.

    A name counts when its base (the name minus any "- Linha X" suffix) is
    said in full, e.g. "TOTVS Assinatura Eletrônica". Two shortcuts: a
    "TOTVS <brand>" name also counts on the bare brand when the brand is in
    _BRAND_WORDS, and an "<X> by <Brand>" name counts on X alone when Brand
    is said anywhere in the meeting ("Process Mining" + "Upflux"). Of line
    variants sharing a base, the ones whose line is also said win.
    """
    # ponytail: a "TOTVS X" name is matched only with "TOTVS" said, because
    # bare remainders are mostly ordinary phrases ("gestão financeira",
    # "performance e gestão"). Unprefixed catalogue names ("Suporte e
    # Sustentação", "Clima e Engajamento") still match as plain phrases, and
    # a product said without "TOTVS" falls to the semantic path. Grow
    # _BRAND_WORDS or transcript_aliases when a real miss shows up.
    said = _normalize(transcript)
    hits = []
    for name in catalogue_names(db):
        base, _, line = _normalize(name).partition(" linha ")
        phrases = [base]
        head, _, brand = base.partition(" by ")
        if brand and _count(brand, said):
            phrases.append(head)
        if base.startswith("totvs ") and base[6:] in _BRAND_WORDS:
            phrases.append(base[6:])
        count = max(
            (_count(phrase, said) for phrase in phrases
             if " " in phrase or phrase in _BRAND_WORDS),
            default=0,
        )
        if count:
            hits.append((name, base, count, bool(line) and _count(line, said) > 0))

    # hit = (name, base, count, line_said)
    bases_with_line_said = {hit[1] for hit in hits if hit[3]}
    hits = [hit for hit in hits if hit[3] or hit[1] not in bases_with_line_said]
    hits.sort(key=lambda hit: (-hit[2], hit[0]))
    return [name for name, *_rest in hits[:top_k]]


def ground_products(
    db: Session, text: str, top_k: int = 5, *, transcript: str | None = None
) -> list[str]:
    """Real catalogue names the meeting mentions, or an empty list.

    With `transcript`, names said literally win outright (see
    find_literal_products); only when none is said does the semantic path
    below run on `text`. Never returns a name the model invented — see module
    docstring for why distance settles the ends of the range and the model
    only the middle. An empty ai.products table or no text to search both
    resolve to `[]`, not an error.
    """
    if transcript:
        literal = find_literal_products(db, transcript, top_k)
        if literal:
            logger.info("product_grounding_branch=literal produtos=%s", literal)
            return literal
    if not text.strip():
        return []
    candidates = find_candidate_products(db, text, top_k)
    if not candidates:
        return []

    closest_product, closest_distance = candidates[0]
    if closest_distance <= settings.product_grounding_confident_distance:
        logger.info(
            "product_grounding_branch=confident distance=%.4f produto=%s",
            closest_distance, closest_product.name,
        )
        return [closest_product.name]

    plausible = [
        (product, distance) for product, distance in candidates
        if distance <= settings.product_grounding_plausible_distance
    ]
    if not plausible:
        logger.info(
            "product_grounding_branch=rejected closest_distance=%.4f", closest_distance,
        )
        return []

    # The transcript was searched and no catalogue name was said: a merely
    # plausible neighbour is a guess. On 10 reference meetings arbitration
    # picked "TOTVS Varejo Index" for a hospital and "App Meus Ativos Fixos" for
    # an ESG pitch; an empty field is better than a wrong one.
    if transcript is not None:
        logger.info(
            "product_grounding_branch=unsaid closest_distance=%.4f", closest_distance,
        )
        return []

    logger.info(
        "product_grounding_branch=arbitration candidatos=%s",
        [product.name for product, _distance in plausible],
    )
    return classify_products(
        text, [(product.name, product.description) for product, _distance in plausible]
    )
