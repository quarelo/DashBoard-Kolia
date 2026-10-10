"""A régua editável: leitura, gravação e simulação sobre o que já está no banco."""
import uuid

import pytest

from src.app.models.analysis import MeetingAnalysis, MeetingChunk
from src.app.models.scoring import ScoringWeight
from src.app.services.scoring_config_service import (
    UnknownMotiveError, declared_motives, list_weights, save_weights, simulate,
)
from src.app.services.scoring_service import DEFAULT_RULER, invalidate_ruler, ruler

SEED = [
    ("AMEACA_CANCELAMENTO", "CHURN", 50),
    ("INSATISFACAO_EXPLICITA", "CHURN", 30),
    ("PEDIDO_EXPANSAO", "OPPORTUNITY", 40),
    ("MENCAO_BUDGET", "OPPORTUNITY", 30),
    ("INTERESSE_NOVO_MODULO", "OPPORTUNITY", 20),
]


@pytest.fixture
def db(sqlite_db):
    for code, side, points in SEED:
        sqlite_db.add(ScoringWeight(
            code=code, side=side, points=points, name=code.title(),
            description=f"descrição de {code}", ruler_version=1))
    sqlite_db.commit()
    return sqlite_db


def _analysis(db, *, chunks: list[dict]) -> uuid.UUID:
    analysis = MeetingAnalysis(
        id=uuid.uuid4(), external_meeting_id=uuid.uuid4(), title="reunião",
        status="DONE", total_chunks=len(chunks),
        final_summary={"risco_churn": {"score": 0}},
    )
    db.add(analysis)
    for index, summary in enumerate(chunks):
        db.add(MeetingChunk(
            id=uuid.uuid4(), analysis_id=analysis.id,
            external_meeting_id=analysis.external_meeting_id,
            chunk_index=index, content="texto", chunk_summary=summary))
    db.commit()
    return analysis.id


class TestRulerFromDatabase:
    def test_weights_come_from_the_table_and_carry_its_version(self, db):
        table = ruler(db)
        assert table.version == 1
        assert table.points["AMEACA_CANCELAMENTO"] == 50

    def test_an_empty_table_falls_back_to_the_constants(self, sqlite_db):
        table = ruler(sqlite_db)
        assert table is DEFAULT_RULER
        assert table.version == 0

    def test_saving_bumps_the_version_and_drops_the_cache(self, db):
        assert ruler(db).points["AMEACA_CANCELAMENTO"] == 50
        saved = save_weights(db, [{"code": "AMEACA_CANCELAMENTO", "points": 70}],
                             "diretor@totvs.com")
        assert saved["ruler_version"] == 2
        # The cache was invalidated by the save, so the next read sees the new value.
        assert ruler(db).points["AMEACA_CANCELAMENTO"] == 70
        assert ruler(db).version == 2

    def test_the_version_is_the_same_on_every_row(self, db):
        save_weights(db, [{"code": "MENCAO_BUDGET", "points": 10}], None)
        versions = {item["code"]: item for item in list_weights(db)["motives"]}
        assert {item["points"] for item in [versions["MENCAO_BUDGET"]]} == {10}
        assert list_weights(db)["ruler_version"] == 2

    def test_a_name_can_be_edited_and_the_code_cannot(self, db):
        save_weights(db, [{"code": "MENCAO_BUDGET", "points": 30,
                           "name": "Verba citada"}], None)
        names = {item["code"]: item["name"] for item in list_weights(db)["motives"]}
        assert names["MENCAO_BUDGET"] == "Verba citada"
        with pytest.raises(UnknownMotiveError):
            save_weights(db, [{"code": "CODIGO_NOVO", "points": 10}], None)


class TestFrequency:
    def test_frequency_counts_meetings_not_chunks(self, db):
        """Calibrar no escuro é o que produziu o score saturado.

        O código que aparece em todas as reuniões não pode valer o mesmo que o
        raro, e a tela só mostra isso se a frequência vier junto do peso.
        """
        _analysis(db, chunks=[
            {"motivos_oportunidade": ["INTERESSE_NOVO_MODULO"], "motivos_churn": []},
            {"motivos_oportunidade": ["INTERESSE_NOVO_MODULO"], "motivos_churn": []},
        ])
        _analysis(db, chunks=[
            {"motivos_oportunidade": ["PEDIDO_EXPANSAO"], "motivos_churn": []},
        ])
        by_code = {item["code"]: item for item in list_weights(db)["motives"]}
        assert list_weights(db)["analysed_meetings"] == 2
        # Duas aparições na mesma reunião contam como uma reunião.
        assert by_code["INTERESSE_NOVO_MODULO"]["meetings"] == 1
        assert by_code["INTERESSE_NOVO_MODULO"]["frequency"] == 0.5
        assert by_code["AMEACA_CANCELAMENTO"]["meetings"] == 0

    def test_a_ruler_whose_top_two_pass_one_hundred_is_flagged(self, db):
        assert list_weights(db)["saturated_sides"] == []
        save_weights(db, [{"code": "PEDIDO_EXPANSAO", "points": 80},
                          {"code": "MENCAO_BUDGET", "points": 80}], None)
        assert list_weights(db)["saturated_sides"] == ["OPPORTUNITY"]


class TestSimulation:
    def test_shares_come_from_how_many_chunks_declared_the_code(self, db):
        analysis_id = _analysis(db, chunks=[
            {"motivos_oportunidade": ["PEDIDO_EXPANSAO"], "motivos_churn": []},
            {"motivos_oportunidade": [], "motivos_churn": []},
            {"motivos_oportunidade": [], "motivos_churn": []},
            {"motivos_oportunidade": [], "motivos_churn": []},
        ])
        shares = declared_motives(db)[analysis_id]["OPPORTUNITY"]
        assert shares == {"PEDIDO_EXPANSAO": 0.25}

    def test_simulation_answers_without_writing_anything(self, db):
        _analysis(db, chunks=[{"motivos_oportunidade": ["PEDIDO_EXPANSAO"],
                               "motivos_churn": ["AMEACA_CANCELAMENTO"]}])
        before = list_weights(db)
        result = simulate(db, {"PEDIDO_EXPANSAO": 10, "AMEACA_CANCELAMENTO": 10})
        assert result["opportunity"]["count"] == 1
        assert result["opportunity"]["median"] == 10
        assert result["churn"]["median"] == 10
        assert list_weights(db)["ruler_version"] == before["ruler_version"]

    def test_a_meeting_with_no_declared_motive_is_a_zero_not_a_gap(self, db):
        _analysis(db, chunks=[{"motivos_oportunidade": [], "motivos_churn": []}])
        result = simulate(db, {code: points for code, _side, points in SEED})
        assert result["opportunity"] == {
            "count": 1, "median": 0, "mean": 0.0,
            "at_100": 0, "at_least_90": 0, "zeros": 1,
        }
