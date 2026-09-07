"""product_service.ground_products: the decision logic around the catalogue
search — distance decides the clear-cut cases, the model only arbitrates the
ambiguous middle. Ranking against the real ai.products table needs Postgres
(see test_hybrid_search.py's docstring for the same reasoning about
rag_service) — find_candidate_products itself is exercised manually in
docs/product-catalog-grounding.md's "como rodar" section instead.
"""
from dataclasses import dataclass

from src.app.core.config import settings
from src.app.services import product_service


@dataclass
class _FakeProduct:
    name: str
    description: str


def test_ground_products_never_calls_the_catalogue_for_blank_text(monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("não deveria buscar candidatos sem texto")

    monkeypatch.setattr(product_service, "find_candidate_products", fail_if_called)

    assert product_service.ground_products(db=None, text="   ") == []


def test_ground_products_returns_empty_list_when_catalogue_has_no_candidates(monkeypatch):
    """An empty ai.products (catalogue not loaded yet) must fail closed to no
    product, never fall back to letting the model name one on its own."""
    monkeypatch.setattr(
        product_service, "find_candidate_products", lambda db, text, top_k: []
    )

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("não deveria classificar sem candidatos")

    monkeypatch.setattr(product_service, "classify_products", fail_if_called)

    assert product_service.ground_products(db=None, text="reunião sobre CRM") == []


def test_ground_products_accepts_a_confident_match_without_calling_the_model(monkeypatch):
    """A very close match is decided by distance alone — no Ollama call spent
    on a case that was never in doubt."""
    monkeypatch.setattr(settings, "product_grounding_confident_distance", 0.20)
    candidates = [
        (_FakeProduct("TOTVS ERP", "Sistema de gestão."), 0.05),
        (_FakeProduct("TOTVS CRM", "Sistema de vendas."), 0.40),
    ]
    monkeypatch.setattr(
        product_service, "find_candidate_products", lambda db, text, top_k: candidates
    )

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("não deveria consultar o modelo num caso óbvio")

    monkeypatch.setattr(product_service, "classify_products", fail_if_called)

    result = product_service.ground_products(db=None, text="cliente elogiou o ERP")

    assert result == ["TOTVS ERP"]


def test_ground_products_rejects_without_the_model_when_nothing_is_close_enough(monkeypatch):
    """Every candidate too far from the text: not even worth asking the model."""
    monkeypatch.setattr(settings, "product_grounding_plausible_distance", 0.45)
    candidates = [
        (_FakeProduct("TOTVS ERP", "Sistema de gestão."), 0.60),
        (_FakeProduct("TOTVS CRM", "Sistema de vendas."), 0.70),
    ]
    monkeypatch.setattr(
        product_service, "find_candidate_products", lambda db, text, top_k: candidates
    )

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError(
            "não deveria consultar o modelo sem nenhum candidato plausível"
        )

    monkeypatch.setattr(product_service, "classify_products", fail_if_called)

    result = product_service.ground_products(db=None, text="reunião sobre férias")

    assert result == []


def test_ground_products_asks_the_model_only_among_the_plausible_candidates(monkeypatch):
    """The ambiguous middle: distance alone can't decide between two close
    candidates, but the model only ever sees the ones distance already vetted
    as plausible — never the one already ruled out (TOTVS ERP here)."""
    monkeypatch.setattr(settings, "product_grounding_confident_distance", 0.20)
    monkeypatch.setattr(settings, "product_grounding_plausible_distance", 0.45)
    candidates = [
        (_FakeProduct("TOTVS RH", "Gestão de recursos humanos."), 0.30),
        (_FakeProduct("App Meu RH", "App do colaborador."), 0.33),
        (_FakeProduct("TOTVS ERP", "Sistema de gestão."), 0.60),
    ]
    seen = {}

    def fake_classify(evidence_text, candidate_pairs, **_kwargs):
        seen["evidence_text"] = evidence_text
        seen["candidate_pairs"] = candidate_pairs
        return ["TOTVS RH"]

    monkeypatch.setattr(
        product_service, "find_candidate_products", lambda db, text, top_k: candidates
    )
    monkeypatch.setattr(product_service, "classify_products", fake_classify)

    result = product_service.ground_products(db=None, text="cliente perguntou sobre o RH")

    assert result == ["TOTVS RH"]
    assert seen["evidence_text"] == "cliente perguntou sobre o RH"
    assert seen["candidate_pairs"] == [
        ("TOTVS RH", "Gestão de recursos humanos."),
        ("App Meu RH", "App do colaborador."),
    ]
