"""A régua de pontuação pelo backend: quem pode salvar e o que chega na IA.

O peso de um motivo move o score de toda reunião nova, então salvar é do diretor
comercial. A validação acontece aqui, antes de gastar uma chamada na IA, e o
`updated_by` é preenchido pelo backend — o navegador não escolhe quem assinou a
mudança.
"""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

RULER = {"ruler_version": 3, "analysed_meetings": 198, "saturated_sides": [],
         "motives": [{"code": "PEDIDO_EXPANSAO", "side": "OPPORTUNITY",
                      "name": "Pedido de ampliação", "description": "...",
                      "points": 30, "meetings": 103, "frequency": 0.52}]}


@pytest.fixture
def api():
    from main import app
    from core.auth import get_current_user
    from schemas.user import RoleEnum
    from services.ia_gateway import get_ia_client

    class User:
        email = "diretor@totvs.com"
        role = RoleEnum.SALES_DIRECTOR

    sent = []

    def ia(request):
        sent.append(request)
        return httpx.Response(200, json=RULER)

    app.dependency_overrides[get_current_user] = lambda: User()
    with httpx.Client(transport=httpx.MockTransport(ia), base_url="http://ia-test") as remote:
        app.dependency_overrides[get_ia_client] = lambda: remote
        client = TestClient(app)
        yield client, sent, User
        client.close()
    app.dependency_overrides.clear()


def test_the_ruler_is_served_with_name_and_real_frequency(api):
    client, _sent, _user = api
    body = client.get("/api/dashboard/scoring").json()
    assert body["ruler_version"] == 3
    assert body["motives"][0]["frequency"] == 0.52


def test_only_the_sales_director_can_save(api):
    client, sent, user = api
    from schemas.user import RoleEnum

    user.role = RoleEnum.USER
    denied = client.put("/api/dashboard/scoring",
                        json={"motives": [{"code": "PEDIDO_EXPANSAO", "points": 30}]})
    assert denied.status_code == 403
    assert not sent, "a IA não deve ser chamada por quem não pode salvar"

    user.role = RoleEnum.SALES_DIRECTOR
    allowed = client.put("/api/dashboard/scoring",
                         json={"motives": [{"code": "PEDIDO_EXPANSAO", "points": 30}]})
    assert allowed.status_code == 200
    assert json.loads(sent[0].content)["updated_by"] == "diretor@totvs.com"


def test_anyone_can_simulate_without_saving(api):
    client, sent, user = api
    from schemas.user import RoleEnum

    user.role = RoleEnum.USER
    response = client.post("/api/dashboard/scoring/simulate",
                           json={"motives": [{"code": "PEDIDO_EXPANSAO", "points": 10}]})
    assert response.status_code == 200
    assert sent[0].method == "POST"
    assert sent[0].url.path == "/scoring/simulate"


@pytest.mark.parametrize("payload, motivo", [
    ({}, "sem lista de motivos"),
    ({"motives": []}, "lista vazia"),
    ({"motives": [{"points": 10}]}, "motivo sem código"),
    ({"motives": [{"code": "PEDIDO_EXPANSAO", "points": 101}]}, "acima de 100"),
    ({"motives": [{"code": "PEDIDO_EXPANSAO", "points": -1}]}, "abaixo de 0"),
    ({"motives": [{"code": "PEDIDO_EXPANSAO", "points": "30"}]}, "pontos em texto"),
    # `True` é `int` em Python e viraria 1 ponto sem o teste de bool.
    ({"motives": [{"code": "PEDIDO_EXPANSAO", "points": True}]}, "booleano"),
])
def test_invalid_rulers_are_refused_before_reaching_the_ia(api, payload, motivo):
    client, sent, _user = api
    response = client.put("/api/dashboard/scoring", json=payload)
    assert response.status_code == 422, motivo
    assert not sent, f"{motivo}: não deveria chegar na IA"
