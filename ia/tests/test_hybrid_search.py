"""Hybrid retrieval: the two searches fail differently, so both run.

Vector search matches on topic — asked about values it returned passages about
"leads" and "ticket médio" and none of the seven that name a price. Lexical search
ranks by term frequency — asked about boleto it drowned the two passages that
discuss it under seventy-nine repeating "falaram". Fusing by rank covers each
one's blind spot without either having to be right on its own.

Ranking against a live corpus needs Postgres; these cover the pieces that decide
what gets searched and how the two lists merge.
"""
import pytest

from src.app.services.rag_service import RRF_K, _fuse, _lexical_query


class TestFusion:
    def test_a_passage_only_one_method_found_still_competes(self):
        """Neither method gets a veto: that is the whole point of running both."""
        scores = _fuse(vector_ids=["a", "b"], lexical_ids=["c"])

        assert set(scores) == {"a", "b", "c"}
        assert scores["c"] == pytest.approx(1 / (RRF_K + 1))

    def test_agreeing_on_a_passage_outranks_leading_one_list(self):
        scores = _fuse(vector_ids=["ambos", "so_vetor"], lexical_ids=["ambos"])

        assert scores["ambos"] > scores["so_vetor"]

    def test_position_decides_within_a_list(self):
        scores = _fuse(vector_ids=["primeiro", "segundo", "terceiro"], lexical_ids=[])

        assert scores["primeiro"] > scores["segundo"] > scores["terceiro"]

    def test_empty_lists_are_not_an_error(self):
        assert _fuse([], []) == {}


class TestLexicalQuery:
    """What gets searched is the question's own words, never a written vocabulary."""

    def test_terms_are_ored_not_anded(self, sqlite_db):
        # plainto_tsquery ANDs, and "prazo data sexta entrega" then matched nothing.
        assert "|" in _lexical_query(sqlite_db, None, "prazo data sexta entrega")

    def test_short_and_noise_words_are_dropped(self, sqlite_db):
        query = _lexical_query(sqlite_db, None, "o que é o boleto?")

        assert "boleto" in query
        assert " o " not in f" {query} "

    def test_a_question_with_nothing_searchable_yields_no_query(self, sqlite_db):
        assert _lexical_query(sqlite_db, None, "e o que?") == ""


class TestAccents:
    """The tsvector keeps accents, so the search term has to keep them too.

    Measured: "conexao" matched 0 of 123 passages where "conexão" matched 2, and
    "orcamento" 0 where "orçamento" matched 33.
    """

    def test_the_search_term_keeps_the_accent_and_the_count_key_drops_it(self):
        from src.app.services.rag_service import _query_terms

        assert ("conexão", "conexao") in _query_terms("O que acontece sem conexão?")

    def test_the_lexical_query_searches_the_accented_word(self, sqlite_db):
        assert "orçamento" in _lexical_query(sqlite_db, None, "qual o orçamento?")


class TestRarityOrder:
    """ts_rank counts repetitions; the passage that answers says the rare word once."""

    def test_one_rare_term_outranks_a_repeated_common_one(self):
        from src.app.services.rag_service import _rarity_order

        hits = [
            ("repete_acontece", {"acontece"}, 0.9),
            ("fala_de_conexao", {"conexao"}, 0.1),
        ]
        ordered = _rarity_order(hits, counts={"acontece": 40, "conexao": 3}, total=120)

        assert ordered == ["fala_de_conexao", "repete_acontece"]

    def test_ts_rank_breaks_a_tie(self):
        from src.app.services.rag_service import _rarity_order

        hits = [("baixo", {"boleto"}, 0.1), ("alto", {"boleto"}, 0.5)]

        assert _rarity_order(hits, counts={"boleto": 5}, total=100) == ["alto", "baixo"]

    def test_without_counts_every_matched_term_weighs_the_same(self):
        from src.app.services.rag_service import _rarity_order

        hits = [("um", {"a"}, 0.9), ("dois", {"a", "b"}, 0.1)]

        assert _rarity_order(hits, counts={}, total=5) == ["dois", "um"]
