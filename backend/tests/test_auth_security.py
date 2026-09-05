"""Security checks for the JWT layer protecting the import/meeting routes.

These do not test happy-path business rules (test_import_api.py covers those).
They assert that every protected route rejects tokens an attacker could forge:
absent, malformed, wrongly signed, `alg: none`, expired, or missing claims.
"""
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

# Every route that must never answer without a valid token.
PROTECTED = [
    ("POST", "/api/imports"),
    ("GET", f"/api/imports/{uuid.uuid4()}"),
    ("GET", "/api/meetings"),
    ("GET", f"/api/meetings/{uuid.uuid4()}"),
    ("POST", f"/api/meetings/{uuid.uuid4()}/analysis"),
    ("GET", f"/api/meetings/{uuid.uuid4()}/analysis"),
]


@pytest.fixture
def anon(database):
    """Client with no Authorization header and no IA gateway wired."""
    from main import app
    from core.database import get_db

    factory, _ = database

    def db_dependency():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = db_dependency
    api = TestClient(app)
    yield api
    api.close()
    app.dependency_overrides.clear()


def call(api, method, path, token=None, scheme="Bearer"):
    headers = {"Authorization": f"{scheme} {token}"} if token is not None else {}
    if method == "POST" and path == "/api/imports":
        return api.post(path, headers=headers,
                        files={"file": ("m.csv", b"ID_MEETING,ANON_TRANSCRICAO\n1,locutor_1 oi.\n")})
    return api.request(method, path, headers=headers)


def token_for(sub="importer@example.com", **overrides):
    from core.config import settings

    claims = {"sub": sub, "role": "USER",
              "exp": datetime.now(timezone.utc) + timedelta(days=1)}
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, settings.secret_key, algorithm=settings.algorithm)


# --- absence and malformed credentials -------------------------------------

@pytest.mark.parametrize("method,path", PROTECTED)
def test_protected_routes_reject_missing_token(anon, method, path):
    response = call(anon, method, path)
    assert response.status_code == 401, f"{method} {path} answered {response.status_code}"
    assert response.headers.get("www-authenticate") == "Bearer"


@pytest.mark.parametrize("method,path", PROTECTED)
def test_protected_routes_reject_garbage_token(anon, method, path):
    assert call(anon, method, path, token="not.a.jwt").status_code == 401


@pytest.mark.parametrize("scheme", ["Basic", "Token", "bearer_typo", ""])
def test_non_bearer_schemes_are_rejected(anon, scheme):
    assert call(anon, "GET", "/api/meetings", token=token_for(), scheme=scheme).status_code == 401


def test_raw_token_without_scheme_is_rejected(anon):
    response = anon.get("/api/meetings", headers={"Authorization": token_for()})
    assert response.status_code == 401


# --- signature forgery ------------------------------------------------------

def test_token_signed_with_another_secret_is_rejected(anon):
    forged = jwt.encode({"sub": "importer@example.com",
                         "exp": datetime.now(timezone.utc) + timedelta(days=1)},
                        "attacker-secret", algorithm="HS256")
    assert call(anon, "GET", "/api/meetings", token=forged).status_code == 401


def test_alg_none_token_is_rejected(anon):
    """Classic algorithm-confusion: unsigned token claiming alg=none."""
    forged = jwt.encode({"sub": "importer@example.com",
                         "exp": datetime.now(timezone.utc) + timedelta(days=1)},
                        key="", algorithm="none")
    assert call(anon, "GET", "/api/meetings", token=forged).status_code == 401


def test_unexpected_algorithm_is_rejected(anon):
    """A token signed with HS512 must not pass an HS256-only decoder."""
    from core.config import settings

    forged = jwt.encode({"sub": "importer@example.com",
                         "exp": datetime.now(timezone.utc) + timedelta(days=1)},
                        settings.secret_key, algorithm="HS512")
    assert call(anon, "GET", "/api/meetings", token=forged).status_code == 401


def test_tampered_payload_is_rejected(anon):
    """Flipping a byte in the payload segment must break verification."""
    header, payload, signature = token_for().split(".")
    tampered = f"{header}.{payload[:-2]}XY.{signature}"
    assert call(anon, "GET", "/api/meetings", token=tampered).status_code == 401


# --- claim validation -------------------------------------------------------

def test_expired_token_is_rejected(anon):
    expired = token_for(exp=datetime.now(timezone.utc) - timedelta(seconds=1))
    assert call(anon, "GET", "/api/meetings", token=expired).status_code == 401


def test_token_without_exp_is_rejected(anon):
    assert call(anon, "GET", "/api/meetings", token=token_for(exp=None)).status_code == 401


def test_token_without_sub_is_rejected(anon):
    assert call(anon, "GET", "/api/meetings", token=token_for(sub=None)).status_code == 401


def test_token_for_unknown_user_is_rejected(anon):
    """A validly signed token whose subject no longer exists must not pass."""
    ghost = token_for(sub="deleted@example.com")
    assert call(anon, "GET", "/api/meetings", token=ghost).status_code == 401


# --- the positive control ---------------------------------------------------

def test_valid_token_is_accepted(anon):
    response = call(anon, "GET", "/api/meetings", token=token_for())
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 0


def test_role_claim_does_not_grant_another_identity(anon):
    """`role` is attacker-controlled data in the payload; only `sub` decides."""
    escalated = token_for(sub="other@example.com", role="SALES_DIRECTOR")
    assert call(anon, "GET", "/api/meetings", token=escalated).status_code == 200


# --- login issues a token that actually works -------------------------------

def test_login_rejects_wrong_password_and_issues_usable_token(anon):
    payload = {"name": "Auth", "email": "auth@example.com",
               "role": "USER", "password": "senha-forte-123"}
    assert anon.post("/register", json=payload).status_code == 201
    assert anon.post("/register", json=payload).status_code == 400

    bad = anon.post("/login", json={"email": payload["email"], "password": "senha-errada-1"})
    assert bad.status_code == 401

    good = anon.post("/login", json={"email": payload["email"], "password": payload["password"]})
    assert good.status_code == 200, good.text
    issued = good.json()["access_token"]
    assert call(anon, "GET", "/api/meetings", token=issued).status_code == 200


def test_registered_password_is_not_stored_in_clear(anon, database):
    from models.user import UserModel
    from sqlalchemy import select

    anon.post("/register", json={"name": "Hash", "email": "hash@example.com",
                                 "role": "USER", "password": "senha-forte-123"})
    factory, _ = database
    with factory() as db:
        stored = db.scalar(select(UserModel).where(UserModel.email == "hash@example.com")).password
    assert "senha-forte-123" not in stored
    assert stored.startswith("$2")
