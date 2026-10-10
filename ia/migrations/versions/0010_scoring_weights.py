"""scoring_weights: pesos e nomes dos motivos no banco

Os pontos de cada motivo eram constantes em `scoring_service.py`, e mudar um peso
exigia deploy — justamente o que o time comercial precisa girar para calibrar os
scores. A tabela guarda peso, nome curto e descrição por código, com um contador
de versão da régua compartilhado por todas as linhas.

A carga inicial usa os valores que já estavam no código, então nada muda de score
no dia em que esta migração sobe. A recalibração é uma edição depois, registrada
na versão da régua.

Revision ID: 0010
Revises: 0009
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# code, side, points, name, description — os pontos são os que já estavam no
# código; o nome e a descrição são o vocabulário da tela.
SEED = [
    ("AMEACA_CANCELAMENTO", "CHURN", 50, "Ameaça de saída",
     "Cliente falou em cancelar, rescindir ou não renovar"),
    ("INSATISFACAO_EXPLICITA", "CHURN", 30, "Insatisfação declarada",
     "Cliente disse, com as próprias palavras, que está insatisfeito"),
    ("MENCAO_CONCORRENTE", "CHURN", 25, "Concorrente na mesa",
     "Cliente citou outro fornecedor ou alternativa"),
    ("RECLAMACAO_PRODUTO", "CHURN", 15, "Falha no produto",
     "Erro, lentidão ou limitação relatada pelo cliente"),
    ("INATIVIDADE_PROLONGADA", "CHURN", 10, "Cliente parado",
     "Sem uso, sem compra ou sem retorno há tempo"),
    ("PEDIDO_EXPANSAO", "OPPORTUNITY", 40, "Pedido de ampliação",
     "Cliente quer mais escopo, licenças ou unidades"),
    ("MENCAO_BUDGET", "OPPORTUNITY", 30, "Verba citada",
     "Valor, orçamento ou investimento mencionado para esta compra"),
    ("PRAZO_DEFINIDO", "OPPORTUNITY", 25, "Prazo combinado",
     "Data concreta acordada para decisão ou entrega"),
    ("INTERESSE_NOVO_MODULO", "OPPORTUNITY", 20, "Interesse em novidade",
     "Cliente pediu para conhecer produto que ainda não usa"),
    ("ELOGIO_CLIENTE", "OPPORTUNITY", 15, "Elogio do cliente",
     "Cliente elogiou produto, entrega ou atendimento"),
]


def upgrade() -> None:
    table = op.create_table(
        "scoring_weights",
        sa.Column("code", sa.Text(), primary_key=True),
        sa.Column("side", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("ruler_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_by", sa.Text(), nullable=True),
        sa.CheckConstraint("points between 0 and 100",
                           name="scoring_weights_points_range"),
        sa.CheckConstraint("side in ('CHURN', 'OPPORTUNITY')",
                           name="scoring_weights_side"),
        schema="ai",
    )
    op.create_index("ix_ai_scoring_weights_side", "scoring_weights", ["side"],
                    schema="ai")
    op.bulk_insert(table, [
        {"code": code, "side": side, "points": points,
         "name": name, "description": description, "ruler_version": 1}
        for code, side, points, name, description in SEED
    ])


def downgrade() -> None:
    op.drop_index("ix_ai_scoring_weights_side", "scoring_weights", schema="ai")
    op.drop_table("scoring_weights", schema="ai")
