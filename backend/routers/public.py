"""Números públicos da landing page.

A página inicial não tem sessão, então não pode ler a dashboard — e era por isso
que ela trazia números escritos à mão no HTML ("500+ reuniões", "87% de
precisão"). Esta rota serve os mesmos quatro números medidos no banco.

Só contagens saem daqui: nenhum nome de cliente, de reunião ou de pessoa, nenhum
texto de transcrição. É a única rota do backend sem autenticação além de
`/login` e `/register`, e ela precisa continuar assim.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.database import get_db

router = APIRouter(prefix="/api/public", tags=["public"])

# A partir deste score a reunião entra na contagem, igual nos dois lados: o
# número tem que querer dizer a mesma coisa em risco e em oportunidade.
HIGH_SCORE = 70

# `~ '^[0-9]+$'` antes do cast: `score` é JSON, e um resumo antigo sem o campo,
# ou com texto nele, derrubaria a página inteira com um erro de conversão.
_STATS = text("""
    SELECT
      count(*) FILTER (WHERE final_summary IS NOT NULL) AS reunioes,
      count(*) FILTER (
        WHERE final_summary -> 'risco_churn' ->> 'score' ~ '^[0-9]+$'
          AND (final_summary -> 'risco_churn' ->> 'score')::int >= :corte
      ) AS riscos,
      count(*) FILTER (
        WHERE final_summary -> 'score_oportunidade' ->> 'score' ~ '^[0-9]+$'
          AND (final_summary -> 'score_oportunidade' ->> 'score')::int >= :corte
      ) AS oportunidades
    FROM ai.meeting_analyses
""")

_PRODUCTS = text("""
    SELECT count(DISTINCT produto)
    FROM ai.meeting_analyses,
         LATERAL jsonb_array_elements_text(final_summary -> 'produto') AS produto
    WHERE jsonb_typeof(final_summary -> 'produto') = 'array'
""")


@router.get("/stats")
def public_stats(db: Session = Depends(get_db)) -> dict:
    row = db.execute(_STATS, {"corte": HIGH_SCORE}).mappings().one()
    return {
        "reunioes_analisadas": int(row["reunioes"] or 0),
        "riscos_detectados": int(row["riscos"] or 0),
        "oportunidades_detectadas": int(row["oportunidades"] or 0),
        "produtos_citados": int(db.execute(_PRODUCTS).scalar_one() or 0),
        "corte_score": HIGH_SCORE,
    }
