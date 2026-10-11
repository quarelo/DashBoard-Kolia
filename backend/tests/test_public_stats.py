"""Os números da landing: abertos, e só contagem.

A página inicial não tem sessão, então esta é a única rota de leitura sem
token. O que ela não pode fazer é passar a devolver nome de cliente, título de
reunião ou texto de transcrição — por isso o teste fixa as duas coisas: que ela
responde sem `Authorization` e que a resposta é um punhado de inteiros.

O SQL em si é exercido contra o Postgres de verdade (as tabelas do schema `ai`
não existem no banco de teste do backend, que só tem o `core`): em 2026-10-10,
`GET /api/public/stats` devolveu 202/40/143/85 na base compartilhada.
"""
import pytest
from fastapi.testclient import TestClient


class FakeResult:
    def __init__(self, row):
        self._row = row

    def mappings(self):
        return self

    def one(self):
        return self._row

    def scalar_one(self):
        return self._row


class FakeSession:
    """Responde as duas consultas da rota na ordem em que ela as faz."""

    def __init__(self):
        self.statements = []

    def execute(self, statement, params=None):
        self.statements.append((str(statement), params))
        if "jsonb_array_elements_text" in str(statement):
            return FakeResult(85)
        return FakeResult({"reunioes": 202, "riscos": 40, "oportunidades": 143})


@pytest.fixture
def api():
    from main import app
    from core.database import get_db

    db = FakeSession()
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    yield client, db
    client.close()
    app.dependency_overrides.clear()


def test_answers_without_a_token(api):
    client, _ = api
    response = client.get("/api/public/stats")
    assert response.status_code == 200


def test_returns_only_counts(api):
    client, _ = api
    body = client.get("/api/public/stats").json()
    assert body == {
        "reunioes_analisadas": 202,
        "riscos_detectados": 40,
        "oportunidades_detectadas": 143,
        "produtos_citados": 85,
        "corte_score": 70,
    }
    assert all(isinstance(value, int) for value in body.values())


def test_uses_the_same_cut_on_both_sides(api):
    """Risco e oportunidade contam a partir do mesmo score, senão os dois
    números da landing não querem dizer a mesma coisa."""
    from routers.public import HIGH_SCORE

    client, db = api
    client.get("/api/public/stats")
    statement, params = db.statements[0]
    assert params == {"corte": HIGH_SCORE}
    assert statement.count(":corte") == 2
