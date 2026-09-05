import json
import csv
import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select


def csv_bytes(ids=("100",), text="locutor_1 Precisamos de 20 licenças."):
    return ("ID_MEETING,ANON_TRANSCRICAO\n" + "".join(f"{id},{text}\n" for id in ids)).encode()


@pytest.fixture
def client(database):
    from main import app
    from core.database import get_db
    from core.security import create_access_token

    factory, _ = database

    def db_dependency():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = db_dependency
    # No lifespan: schema is prepared by the isolated PostgreSQL fixture.
    api = TestClient(app)
    api.headers["Authorization"] = "Bearer " + create_access_token({"sub": "importer@example.com"})
    yield api
    api.close()
    app.dependency_overrides.clear()


def upload(client, data=None, name="meetings.csv"):
    return client.post("/api/imports", files={"file": (name, data or csv_bytes())})


def test_csv_import_is_persisted_without_calling_ia_and_visible_only_to_owner(client):
    from core.security import create_access_token

    response = upload(client)
    assert response.status_code == 201, response.text
    assert response.json()["imported_count"] == 1
    listing = client.get("/api/meetings").json()
    assert listing["total"] == 1
    meeting = listing["items"][0]
    assert meeting["external_id"] == "100"
    assert meeting["analysis_id"] is None
    assert "transcription" not in meeting
    detail = client.get(f"/api/meetings/{meeting['id']}").json()
    assert detail["transcription"] == "locutor_1 Precisamos de 20 licenças."
    client.headers["Authorization"] = "Bearer " + create_access_token({"sub": "other@example.com"})
    assert client.get("/api/meetings").json()["total"] == 0
    assert client.get(f"/api/meetings/{meeting['id']}").status_code == 404
    assert client.get(f"/api/imports/{response.json()['import_id']}").status_code == 404
    assert client.post(f"/api/meetings/{meeting['id']}/analysis").status_code == 404


def test_same_file_renamed_and_equivalent_json_are_rejected(client):
    assert upload(client).status_code == 201
    assert upload(client, name="renamed.csv").status_code == 409
    equivalent = json.dumps([{"ID_MEETING": "100", "ANON_TRANSCRICAO": "locutor_1 Precisamos de 20 licenças."}]).encode()
    response = upload(client, equivalent, "converted.json")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "DUPLICATE_IMPORT"
    assert client.get("/api/meetings").json()["total"] == 1


def test_mixed_file_imports_new_meetings_and_versions_changed_ones(client):
    assert upload(client).status_code == 201
    result = upload(client, csv_bytes(("100", "101"))).json()
    assert (result["imported_count"], result["skipped_count"]) == (1, 1)
    changed = upload(client, csv_bytes(("100", "102"), text="Conteúdo alterado.")).json()
    # 102 is new; 100 already existed with different text, so it gains a version.
    assert (changed["imported_count"], changed["versioned_count"], changed["skipped_count"]) == (1, 1, 0)
    listing = client.get("/api/meetings").json()
    assert listing["total"] == 3
    assert {(m["external_id"], m["version"]) for m in listing["items"]} == {
        ("100", 2), ("101", 1), ("102", 1)}


def test_changed_transcription_creates_version_without_touching_the_previous_one(client):
    upload(client, csv_bytes(("100",), text="Texto original."))
    first = client.get("/api/meetings").json()["items"][0]
    upload(client, csv_bytes(("100",), text="Texto corrigido."))

    listing = client.get("/api/meetings").json()
    assert listing["total"] == 1, "a listagem padrão mostra apenas a versão vigente"
    current = listing["items"][0]
    assert (current["version"], current["id"] != first["id"]) == (2, True)
    assert client.get(f"/api/meetings/{current['id']}").json()["transcription"] == "Texto corrigido."

    # The superseded row survives untouched and is still addressable by its own id.
    previous = client.get(f"/api/meetings/{first['id']}").json()
    assert (previous["version"], previous["transcription"]) == (1, "Texto original.")
    assert client.get("/api/meetings?include_versions=true").json()["total"] == 2


def test_versions_endpoint_lists_history_oldest_first(client):
    upload(client, csv_bytes(("100",), text="Texto original."))
    upload(client, csv_bytes(("100",), text="Texto corrigido."))
    upload(client, csv_bytes(("100",), text="Texto final."))
    current = client.get("/api/meetings").json()["items"][0]

    history = client.get(f"/api/meetings/{current['id']}/versions").json()
    assert history["external_id"] == "100"
    assert [m["version"] for m in history["items"]] == [1, 2, 3]


def test_new_version_gets_its_own_analysis_and_leaves_the_previous_analysis_intact(client, monkeypatch):
    import services.ia_gateway as gateway

    upload(client, csv_bytes(("100",), text="Texto original."))
    first = client.get("/api/meetings").json()["items"][0]
    keys = []

    def fake_request(client_, method, path, **kwargs):
        keys.append(kwargs.get("headers", {}).get("Idempotency-Key"))
        return {"analysis_id": str(uuid4()), "status": "QUEUED",
                "meeting_id": kwargs["json"]["meeting_id"]}

    monkeypatch.setattr(gateway, "request_ia", fake_request)
    assert client.post(f"/api/meetings/{first['id']}/analysis").status_code == 202

    upload(client, csv_bytes(("100",), text="Texto corrigido."))
    current = client.get("/api/meetings").json()["items"][0]
    assert client.post(f"/api/meetings/{current['id']}/analysis").status_code == 202

    # Distinct rows mean distinct idempotency keys, so the IA builds separate chunks.
    assert len(set(keys)) == 2
    stored = client.get(f"/api/meetings/{first['id']}").json()["analysis_id"]
    assert stored is not None
    assert stored != client.get(f"/api/meetings/{current['id']}").json()["analysis_id"]


def test_reverting_to_previous_content_does_not_grow_a_new_version(client):
    upload(client, csv_bytes(("100",), text="Texto A."))
    upload(client, csv_bytes(("100",), text="Texto B."))
    reverted = upload(client, csv_bytes(("100",), text="Texto A."), name="volta.csv")
    assert reverted.status_code == 409
    assert reverted.json()["detail"]["code"] == "DUPLICATE_IMPORT"
    assert client.get("/api/meetings?include_versions=true").json()["total"] == 2


def test_no_new_meetings_in_different_file_is_rejected(client):
    assert upload(client, csv_bytes(("100", "101"))).status_code == 201
    subset = upload(client)
    assert subset.status_code == 409
    assert subset.json()["detail"]["code"] == "DUPLICATE_IMPORT"


def test_invalid_input_and_missing_token_do_not_persist(client):
    assert upload(client, b"ID_MEETING,ANON_TRANSCRICAO\n100,\n").status_code == 422
    assert upload(client, name="input.exe").status_code == 415
    assert client.get("/api/meetings").json()["total"] == 0
    del client.headers["Authorization"]
    assert upload(client).status_code == 401


def test_simultaneous_uploads_create_one_import(database):
    from models.meeting import ImportedMeeting, MeetingImport
    from services.meeting_import_service import import_meetings
    from services.meeting_parser import ImportValidationError, parse_meeting_file

    factory, (owner, _) = database
    parsed = parse_meeting_file(csv_bytes(), "input.csv")
    barrier = Barrier(2)

    def attempt():
        with factory() as db:
            barrier.wait(timeout=5)
            try:
                import_meetings(db, owner, "input.csv", parsed)
                return 201
            except ImportValidationError as error:
                return error.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(results) == [201, 409]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(MeetingImport)) == 1
        assert db.scalar(select(func.count()).select_from(ImportedMeeting)) == 1


def test_analysis_uses_saved_transcription_and_reuses_analysis_id(client):
    from main import app
    from services.ia_gateway import get_ia_client

    assert upload(client).status_code == 201
    meeting_id = client.get("/api/meetings").json()["items"][0]["id"]
    analysis_id = str(uuid4())
    requests = []

    def ia(request):
        requests.append(request)
        if request.method == "POST":
            payload = json.loads(request.content)
            assert payload["meeting_id"] == meeting_id
            assert payload["transcription"] == "[LOCUTOR 1]: Precisamos de 20 licenças."
            assert len(request.headers["Idempotency-Key"]) == 64
        return httpx.Response(202 if request.method == "POST" else 200, json={
            "analysis_id": analysis_id, "meeting_id": meeting_id, "status": "PROCESSING",
            "summary_is_final": False,
        })

    with httpx.Client(transport=httpx.MockTransport(ia), base_url="http://ia-test") as remote:
        app.dependency_overrides[get_ia_client] = lambda: remote
        first = client.post(f"/api/meetings/{meeting_id}/analysis")
        again = client.post(f"/api/meetings/{meeting_id}/analysis")
    assert first.status_code == again.status_code == 202
    assert first.json()["analysis_id"] == again.json()["analysis_id"] == analysis_id
    assert sum(r.method == "POST" for r in requests) == 1


def test_timeout_retry_keeps_same_idempotency_key(client):
    from main import app
    from services.ia_gateway import get_ia_client

    upload(client)
    meeting_id = client.get("/api/meetings").json()["items"][0]["id"]
    keys = []

    def ia(request):
        keys.append(request.headers["Idempotency-Key"])
        raise httpx.ReadTimeout("uncertain delivery", request=request)

    with httpx.Client(transport=httpx.MockTransport(ia), base_url="http://ia-test") as remote:
        app.dependency_overrides[get_ia_client] = lambda: remote
        for _ in range(2):
            assert client.post(f"/api/meetings/{meeting_id}/analysis").status_code == 503
    assert len(keys) == 2 and keys[0] == keys[1]


def test_summary_and_rag_readiness_are_separate(client):
    from services.ia_gateway import readiness

    assert readiness({"status": "EMBEDDING", "summary_is_final": True}) == {"summary_ready": True, "rag_ready": False}
    assert readiness({"status": "DASHBOARD_READY_WITH_EMBEDDING_ERROR", "summary_is_final": True}) == {"summary_ready": True, "rag_ready": False}
    assert readiness({"status": "DONE", "summary_is_final": True}) == {"summary_ready": True, "rag_ready": True}


def test_real_dataset_csv_then_json_imports_500_only_once(client):
    path = Path(__file__).resolve().parents[2] / "ia" / "dataset_tratado_revisado.csv"
    if not path.exists():
        pytest.skip("Local POC dataset not present")
    content = path.read_bytes()
    first = upload(client, content, path.name)
    assert first.status_code == 201, first.text
    assert first.json()["imported_count"] == 500
    rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
    second = upload(client, json.dumps(list(reversed(rows))).encode(), "converted.json")
    assert second.status_code == 409
    listing = client.get("/api/meetings?limit=100").json()
    assert listing["total"] == 500
    assert len(listing["items"]) == 100
    assert all(row["analysis_id"] is None for row in listing["items"])


def test_upload_body_limit_is_enforced_before_multipart_parsing(client):
    oversized = b"x" * (6 * 1024 * 1024)
    response = client.post("/api/imports", content=oversized, headers={"Content-Type": "multipart/form-data; boundary=x"})
    assert response.status_code == 413
    assert client.get("/api/meetings").json()["total"] == 0


def test_streamed_upload_without_content_length_is_also_limited(client):
    def stream():
        for _ in range(6):
            yield b"x" * 1024 * 1024

    response = client.post("/api/imports", content=stream(), headers={"Content-Type": "multipart/form-data; boundary=x"})
    assert response.status_code == 413
    assert client.get("/api/meetings").json()["total"] == 0


def test_concurrent_analysis_clicks_submit_once(client, database):
    from main import app
    from services.ia_gateway import get_ia_client

    upload(client)
    meeting_id = client.get("/api/meetings").json()["items"][0]["id"]
    analysis_id = str(uuid4())
    barrier = Barrier(2)
    methods = []

    def ia(request):
        methods.append(request.method)
        return httpx.Response(202 if request.method == "POST" else 200, json={
            "analysis_id": analysis_id, "meeting_id": meeting_id, "status": "PROCESSING",
        })

    # Separate clients without lifespan to avoid production startup in this test.
    def click():
        api = TestClient(app)
        api.headers.update(client.headers)
        try:
            barrier.wait(timeout=5)
            return api.post(f"/api/meetings/{meeting_id}/analysis")
        finally:
            api.close()

    with httpx.Client(transport=httpx.MockTransport(ia), base_url="http://ia-test") as remote:
        app.dependency_overrides[get_ia_client] = lambda: remote
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: click(), range(2)))
    assert [r.status_code for r in responses] == [202, 202]
    assert methods.count("POST") == 1


def test_identifier_too_large_is_a_validation_error_not_database_error(client):
    oversized_id = "é" * 513
    response = upload(client, csv_bytes((oversized_id,)))
    assert response.status_code == 422
    assert client.get("/api/meetings").json()["total"] == 0
