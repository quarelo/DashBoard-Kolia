"""A busca da lista de reuniões filtra a tabela inteira, não a página.

Ela rodava no cliente, sobre os 50 itens que a página havia carregado
(`frontend/src/pages/Meetings.tsx`), então procurar a reunião 1153738 — que
estava na página 2 das 550 análises — não achava nada. O teste fixa as duas
pontas que isso exige: o termo chega ao SQL como parâmetro, e o `total` passa a
contar os resultados, porque é dele que a tela calcula o número de páginas.
"""
from types import SimpleNamespace
from uuid import uuid4

from services import analysis_read


class FakeResult:
    def __init__(self, rows, scalar):
        self._rows = rows
        self._scalar = scalar

    def all(self):
        return self._rows

    def scalar(self):
        return self._scalar


class FakeSession:
    """Guarda cada SQL executado, para conferir o que foi parar no banco."""

    def __init__(self, rows=()):
        self.rows = list(rows)
        self.executed: list[tuple[str, dict]] = []

    def execute(self, statement, params=None):
        sql = str(statement)
        self.executed.append((sql, dict(params or {})))
        if sql.lstrip().upper().startswith("SELECT COUNT"):
            return FakeResult([], len(self.rows))
        return FakeResult(self.rows, None)


def _row(title, external_id):
    return SimpleNamespace(
        analysis_id=uuid4(), external_meeting_id=uuid4(), title=title,
        status="DONE", summary_stage="FINAL", summary_is_final=True,
        error_message=None, created_at=None, updated_at=None,
        total_tokens=0, total_chunks=0, final_summary={},
        meeting_id=uuid4(), meeting_external_id=external_id, meeting_metadata={},
    )


def test_search_becomes_a_bound_parameter():
    where, params = analysis_read._build_filters(search="1153738")
    assert params["search"] == "%1153738%"
    # O número da reunião pode estar no título ou no external_id, e a busca
    # também cobre produto e persona, como fazia no cliente.
    for column in ("a.title", "m.external_id", "'produto'", "'persona'"):
        assert column in where


def test_blank_search_adds_no_clause():
    assert analysis_read._build_filters(search="   ") == ("", {})
    assert analysis_read._build_filters(search=None) == ("", {})


def test_search_reaches_the_count_and_the_rows():
    db = FakeSession([_row("Reunião 1153738", "1153738")])
    result = analysis_read.list_analyses(db, 0, 50, search="1153738")

    count_sql, count_params = db.executed[0]
    rows_sql, rows_params = db.executed[1]
    assert count_params["search"] == rows_params["search"] == "%1153738%"
    # Sem o JOIN a contagem não enxerga `m.external_id` e o SQL nem compila.
    assert "LEFT JOIN core.meetings" in count_sql
    assert "LIMIT :limit OFFSET :offset" in rows_sql
    # O total é o dos resultados, não o das 550: é ele que dá o número de
    # páginas na tela, e com 550 a paginação ofereceria 11 páginas vazias.
    assert result["total"] == 1
    assert [item["title"] for item in result["items"]] == ["Reunião 1153738"]


def test_no_search_keeps_the_plain_listing():
    db = FakeSession([_row("Reunião 1", "1"), _row("Reunião 2", "2")])
    result = analysis_read.list_analyses(db, 0, 50)

    count_sql, count_params = db.executed[0]
    assert "search" not in count_params
    assert "WHERE" not in count_sql
    assert result["total"] == 2
