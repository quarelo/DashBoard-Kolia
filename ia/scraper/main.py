"""One-time loader for the TOTVS product catalogue.

    cd ia
    python -m scraper.main

This is a carga inicial, not a sync job: it does not run on a schedule, does
not upsert, and does not track changes to the live site. Rerunning it is
refused whenever ai.products already has rows, so an accidental second run
cannot silently double every product; pass --force to load anyway (e.g. after
manually clearing the table for a fresh load).
"""
import argparse
import logging
import sys

from scraper.fetch import DEFAULT_CATALOGUE_URL, fetch_catalogue_html
from scraper.ingest import catalogue_already_loaded, ingest_products
from scraper.parser import parse_catalogue
from src.app.core.database import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("scraper")


def main() -> None:
    parser = argparse.ArgumentParser(description="Carrega o catálogo de produtos TOTVS.")
    parser.add_argument("--url", default=DEFAULT_CATALOGUE_URL)
    parser.add_argument(
        "--force", action="store_true",
        help="Executa mesmo que ai.products já tenha linhas (não limpa as existentes antes).",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        if catalogue_already_loaded(db) and not args.force:
            sys.exit(
                "ai.products já contém dados. Esta é uma carga única: limpe a tabela "
                "manualmente antes de repetir, ou rode com --force para carregar mesmo assim."
            )

        logger.info("[SCRAPER] Iniciando...")
        html = fetch_catalogue_html(args.url)
        logger.info("[SCRAPER] Página carregada.")
        products = parse_catalogue(html)
        logger.info("[SCRAPER] %d produtos encontrados.", len(products))

        report = ingest_products(db, products)

        logger.info("[FINISHED]")
        logger.info("Produtos encontrados: %d", report.found)
        logger.info("Processados: %d", report.inserted)
        logger.info("Falhas: %d", len(report.failed))
        for name, error in report.failed:
            logger.info("  - %s: %s", name, error)
        if report.failed:
            sys.exit(1)


if __name__ == "__main__":
    main()
