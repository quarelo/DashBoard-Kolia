"""Manual sanity check for the loaded catalogue: does similarity search make sense?

    cd ia
    python -m scraper.search_sample "software para gestão empresarial"

Embeds the query with the same nomic-embed-text call used for ingestion, then
runs the exact cosine-distance query the future chunk -> top-5-candidates step
will use (see rag_service.search_analysis_chunks for the same pattern applied
to meeting chunks instead of products).
"""
import sys

from sqlalchemy import select

from src.app.core.database import SessionLocal
from src.app.models.product import Product
from src.app.services.llm_service import generate_embedding

DEFAULT_QUERY = "software para gestão empresarial"


def top_matches(query: str, top_k: int = 5) -> list[tuple[str, str, float]]:
    embedding = generate_embedding(query)
    distance = Product.embedding.cosine_distance(embedding)
    with SessionLocal() as db:
        rows = db.execute(
            select(Product.name, Product.description, distance.label("distance"))
            .order_by(distance.asc())
            .limit(top_k)
        ).all()
    return [(name, description, float(dist)) for name, description, dist in rows]


def main() -> None:
    query = " ".join(sys.argv[1:]) or DEFAULT_QUERY
    print(f'Consulta: "{query}"\n')
    for name, description, distance in top_matches(query):
        print(f"- {name}  (distância={distance:.4f})")
        print(f"    {description[:160]}{'...' if len(description) > 160 else ''}")


if __name__ == "__main__":
    main()
