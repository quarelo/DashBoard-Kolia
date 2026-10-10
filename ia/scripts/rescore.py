"""Recalcula o score das análises já gravadas, sem LLM.

Passo 8 de `docs/scoring-calibration-plan.md`, e por isso não roda sozinho: o time
pediu para manter os números antigos como feedback, então o recálculo é um pedido
explícito. Sem `--apply` o script só mostra o que mudaria.

    docker compose exec ia-service python -m scripts.rescore
    docker compose exec ia-service python -m scripts.rescore --apply

Só os scores e a versão da régua são reescritos; o resto do `final_summary`, que
veio do modelo, fica como está.
"""
import argparse

from sqlalchemy import select

from src.app.core.database import SessionLocal
from src.app.models.analysis import MeetingAnalysis, MeetingChunk
from src.app.services.analysis_service import build_compact_final_summary
from src.app.services.scoring_service import ruler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="grava; sem isto o script só compara")
    args = parser.parse_args()

    with SessionLocal() as db:
        table = ruler(db)
        analyses = db.execute(
            select(MeetingAnalysis).where(MeetingAnalysis.final_summary.is_not(None))
        ).scalars().all()
        changed = 0
        for analysis in analyses:
            chunks = db.execute(
                select(MeetingChunk)
                .where(MeetingChunk.analysis_id == analysis.id)
                .order_by(MeetingChunk.chunk_index)
            ).scalars().all()
            summaries = [chunk.chunk_summary for chunk in chunks
                         if chunk.chunk_summary is not None]
            if not summaries:
                continue
            scored = build_compact_final_summary(
                summaries,
                [chunk.clean_content or chunk.content for chunk in chunks],
                weights=table,
            )
            before = (analysis.final_summary.get("risco_churn", {}).get("score"),
                      analysis.final_summary.get("score_oportunidade", {}).get("score"))
            after = (scored["risco_churn"]["score"], scored["score_oportunidade"]["score"])
            if before == after:
                continue
            changed += 1
            print(f"{analysis.id} churn {before[0]} -> {after[0]} "
                  f"oportunidade {before[1]} -> {after[1]}")
            if args.apply:
                analysis.final_summary = {
                    **analysis.final_summary,
                    "risco_churn": scored["risco_churn"],
                    "score_oportunidade": scored["score_oportunidade"],
                }
        print(f"\nanálises={len(analyses)} mudariam={changed} "
              f"régua={table.version} aplicado={args.apply}")
        if args.apply:
            db.commit()


if __name__ == "__main__":
    main()
