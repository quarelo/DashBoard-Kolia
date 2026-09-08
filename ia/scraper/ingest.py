"""Turn parsed catalogue products into persisted rows with embeddings.

Reuses the IA service's own Ollama client (`generate_embedding`) and database
session instead of a parallel implementation, so the products table's vector
dimension and Ollama error handling can never drift from what the
meeting-analysis pipeline already relies on.
"""
import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from scraper.parser import CatalogueProduct
from src.app.models.product import Product
from src.app.services.llm_service import generate_embedding

logger = logging.getLogger("scraper")


@dataclass
class IngestReport:
    found: int = 0
    inserted: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)


def catalogue_already_loaded(db: Session) -> bool:
    return db.scalar(select(Product.id).limit(1)) is not None


def ingest_products(db: Session, products: list[CatalogueProduct]) -> IngestReport:
    """Embed and insert each product. One failure never aborts the batch."""
    report = IngestReport(found=len(products))
    for product in products:
        try:
            logger.info("[EMBEDDING] %s", product.name)
            content = f"{product.name}\n\n{product.description}"
            embedding = generate_embedding(content)
            db.add(Product(
                name=product.name,
                description=product.description,
                source_url=product.source_url,
                content=content,
                embedding=embedding,
            ))
            db.commit()
            report.inserted += 1
            logger.info("[DATABASE] %s salvo.", product.name)
        except Exception as error:  # noqa: BLE001 - one bad product must not abort the batch
            db.rollback()
            report.failed.append((product.name, f"{type(error).__name__}: {error}"))
            logger.error(
                "[ERRO] produto=%s etapa=embedding_ou_insert erro=%s",
                product.name, error,
            )
    return report
