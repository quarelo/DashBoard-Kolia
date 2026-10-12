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


_CATALOGUE = [
    "TOTVS Fluig",
    "App My Fluig",
    "Suporte e Sustentação",
    "TOTVS Saúde Planos - Linha Protheus",
    "TOTVS Saúde Planos - Linha Datasul",
    "TOTVS Assinatura Eletrônica",
    "App Minha Assinatura Eletrônica",
    "TOTVS RH Ponto Eletrônico - Linha RM",
    "TOTVS Transmite",
    "TOTVS Gestão Financeira - Linha Gesplan",
    "App Minha Produção - Linha Protheus",
    "Process Mining by Upflux",
    "Ciclo de Receita by UpFlux",
    "TOTVS Performance e Gestão",
    "TOTVS Analytics",
    "TOTVS Agendamentos",
    "PaaS",
    "Gestão de Vendas by Retail App",
]


def _literal_only(monkeypatch, catalogue=_CATALOGUE):
    monkeypatch.setattr(product_service, "catalogue_names", lambda db: catalogue)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("menção literal não deveria cair na busca semântica")

    monkeypatch.setattr(product_service, "find_candidate_products", fail_if_called)


def _ground(transcript, text="produto citado"):
    return product_service.ground_products(db=None, text=text, transcript=transcript)


def test_literal_brand_word_wins_over_semantic_guess(monkeypatch):
    _literal_only(monkeypatch)
    transcript = "O contrato de suporte cobre o Fluig. O Fluig integra com o Proteus."

    assert _ground(transcript) == ["TOTVS Fluig"]


def test_literal_name_after_alias_fix(monkeypatch):
    _literal_only(monkeypatch)
    transcript = "Vamos usar a Totus Assinatura Eletrônica nos contratos."

    assert _ground(transcript) == ["TOTVS Assinatura Eletrônica"]


def test_literal_alias_names_product_and_generic_phrases_do_not(monkeypatch):
    _literal_only(monkeypatch)
    transcript = (
        "O Transmit manda as notas. A minha produção cresceu. "
        "O Transmit resolve a gestão financeira."
    )

    assert _ground(transcript) == ["TOTVS Transmite"]


def test_literal_by_name_needs_its_brand_said(monkeypatch):
    _literal_only(monkeypatch)
    transcript = "Process mining mostra o gargalo; o AppFlux faz o process mining."

    assert _ground(transcript) == ["Process Mining by Upflux"]


def test_literal_ranks_by_mentions_and_caps_at_top_k(monkeypatch):
    _literal_only(monkeypatch)
    transcript = (
        "Totvs Assinatura Eletrônica. Fluig, Fluig e Fluig. "
        "Falamos de suporte e sustentação."
    )

    assert product_service.ground_products(
        db=None, text="x", top_k=2, transcript=transcript
    ) == ["TOTVS Fluig", "Suporte e Sustentação"]


def test_literal_prefers_the_line_variant_whose_line_is_said(monkeypatch):
    _literal_only(monkeypatch)
    transcript = "O TOTVS Saúde Planos roda no Protheus."

    assert _ground(transcript) == ["TOTVS Saúde Planos - Linha Protheus"]


def test_literal_runs_even_with_empty_grounding_query(monkeypatch):
    _literal_only(monkeypatch)

    assert _ground("Abrimos chamado no Fluig.", text="") == ["TOTVS Fluig"]


def test_generic_words_fall_back_to_the_semantic_path(monkeypatch):
    """No catalogue name said (only generic words like "analytics",
    "agendamentos", "PaaS", "gestão de vendas" without its brand): the
    existing semantic path decides, unchanged."""
    monkeypatch.setattr(product_service, "catalogue_names", lambda db: _CATALOGUE)
    monkeypatch.setattr(settings, "product_grounding_confident_distance", 0.20)
    candidates = [(_FakeProduct("TOTVS Analytics", "BI."), 0.05)]
    monkeypatch.setattr(
        product_service, "find_candidate_products", lambda db, text, top_k: candidates
    )
    transcript = (
        "Precisamos de analytics, agendamentos e PaaS para a gestão de vendas; "
        "o processo vai fluir melhor."
    )

    assert _ground(transcript, text="painel de indicadores") == ["TOTVS Analytics"]


def test_unsaid_product_skips_arbitration_and_stays_empty(monkeypatch):
    """With the transcript searched and no name said, a merely plausible
    neighbour is a guess: arbitration picked "TOTVS Varejo Index" for a hospital."""
    monkeypatch.setattr(product_service, "catalogue_names", lambda db: _CATALOGUE)
    monkeypatch.setattr(settings, "product_grounding_confident_distance", 0.20)
    monkeypatch.setattr(settings, "product_grounding_plausible_distance", 0.45)
    candidates = [(_FakeProduct("TOTVS Varejo Index", "Varejo."), 0.35)]
    monkeypatch.setattr(
        product_service, "find_candidate_products", lambda db, text, top_k: candidates
    )
    monkeypatch.setattr(
        product_service, "classify_products",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no arbitration")),
    )

    assert _ground("lentidão na prescrição do hospital", text="painel lento") == []


def test_without_transcript_the_catalogue_names_are_never_read(monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("sem transcrição não há busca literal")

    monkeypatch.setattr(product_service, "catalogue_names", fail_if_called)
    monkeypatch.setattr(
        product_service, "find_candidate_products", lambda db, text, top_k: []
    )

    assert product_service.ground_products(db=None, text="reunião sobre o Fluig") == []
