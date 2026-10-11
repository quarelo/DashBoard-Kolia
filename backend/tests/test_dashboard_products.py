"""A tela de Produtos lista todos os produtos citados, não só o Top 10.

Ela lia `top_produtos` do `/executive`, que corta em 10 para o gráfico da
Dashboard; com 303 análises no banco havia bem mais de cem produtos citados e a
tela mostrava dez. O teste fixa as duas pontas: `/executive` continua em 10 e
`/products` devolve todos, na mesma ordem.
"""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

PRODUCTS = [f"Produto {index:02d}" for index in range(15)]


def _row(products):
    return SimpleNamespace(
        analysis_id=uuid4(), external_meeting_id=uuid4(), meeting_external_id=None,
        title="Reunião 1", meeting_metadata={},
        final_summary={"produto": products},
    )


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeSession:
    def __init__(self):
        # "Produto 00" aparece em 15 reuniões, "Produto 14" em uma: a ordem
        # esperada é a da lista.
        self.rows = [_row(PRODUCTS[:count]) for count in range(1, len(PRODUCTS) + 1)]

    def execute(self, statement, params=None):
        return FakeResult(self.rows)


@pytest.fixture
def client():
    from main import app
    from core.auth import get_current_user
    from core.database import get_db

    app.dependency_overrides[get_db] = lambda: FakeSession()
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1, role="USER")
    test_client = TestClient(app)
    yield test_client
    test_client.close()
    app.dependency_overrides.clear()


def test_products_returns_every_cited_product(client):
    body = client.get("/api/dashboard/products").json()
    assert body["total"] == len(PRODUCTS)
    assert [item["nome"] for item in body["items"]] == PRODUCTS


def test_executive_keeps_its_top_ten(client):
    body = client.get("/api/dashboard/executive").json()
    assert [item["nome"] for item in body["top_produtos"]] == PRODUCTS[:10]
