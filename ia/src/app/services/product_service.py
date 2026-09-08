"""Ground `produto` against the real TOTVS catalogue instead of letting the
model name one from memory.

Distance decides the clear-cut cases; the model only arbitrates real
ambiguity, and only once per whole analysis, not per chunk. Full rationale
(why hybrid, why once per analysis, threshold values) in
docs/product-catalog-grounding.md — keep that doc in sync with this file.
"""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.app.core.config import settings
from src.app.models.product import Product
from src.app.services.llm_service import classify_products, generate_embedding

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


def ground_products(db: Session, text: str, top_k: int = 5) -> list[str]:
    """Real catalogue names the meeting mentions, or an empty list.

    Never returns a name the model invented — see module docstring for why
    distance settles the ends of the range and the model only the middle. An
    empty ai.products table or no text to search both resolve to `[]`, not an
    error.
    """
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

    logger.info(
        "product_grounding_branch=arbitration candidatos=%s",
        [product.name for product, _distance in plausible],
    )
    return classify_products(
        text, [(product.name, product.description) for product, _distance in plausible]
    )
