"""Simula réguas de pontuação sobre as análises já gravadas, sem LLM.

É a ferramenta do passo 2 de `docs/scoring-calibration-plan.md`: iterar peso e
fórmula custa segundos, porque os motivos de cada chunk já estão no banco. Nada é
escrito.

    docker compose exec ia-service python -m scripts.score_sim
    docker compose exec ia-service python -m scripts.score_sim \\
        --points INTERESSE_NOVO_MODULO=5 PEDIDO_EXPANSAO=30
"""
import argparse

from src.app.core.database import SessionLocal
from src.app.services.scoring_config_service import list_weights, simulate

# A recalibração proposta no passo 3 do plano, para comparar de um comando só.
PLAN_POINTS = {
    "AMEACA_CANCELAMENTO": 50,
    "INSATISFACAO_EXPLICITA": 20,
    "MENCAO_CONCORRENTE": 20,
    "RECLAMACAO_PRODUTO": 15,
    "INATIVIDADE_PROLONGADA": 10,
    "PEDIDO_EXPANSAO": 30,
    "MENCAO_BUDGET": 20,
    "PRAZO_DEFINIDO": 25,
    "INTERESSE_NOVO_MODULO": 5,
    "ELOGIO_CLIENTE": 10,
}


def parse_points(pairs: list[str]) -> dict[str, int]:
    points = {}
    for pair in pairs:
        code, _, value = pair.partition("=")
        points[code.strip()] = int(value)
    return points


def show(title: str, result: dict) -> None:
    print(f"\n{title}")
    for side in ("churn", "opportunity"):
        stats = result[side]
        print(f"  {side:12s} " + "  ".join(
            f"{key}={value}" for key, value in stats.items()))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--points", nargs="*", default=[],
                        help="CODIGO=pontos, sobrepõe a régua em vigor")
    args = parser.parse_args()

    with SessionLocal() as db:
        current = {item["code"]: item["points"] for item in list_weights(db)["motives"]}
        rulers = {"régua em vigor": current, "proposta do plano": {**current, **PLAN_POINTS}}
        if args.points:
            rulers["--points"] = {**current, **parse_points(args.points)}
        for title, points in rulers.items():
            show(title, simulate(db, points))


if __name__ == "__main__":
    main()
