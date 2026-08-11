from threading import Event, Lock
from types import SimpleNamespace
from uuid import uuid4

from src.app.services import analysis_worker


class FakeSession:
    def get(self, _model, _analysis_id):
        return SimpleNamespace(final_summary=None, status="PROCESSING")

    def close(self):
        pass


def test_worker_serializes_ollama_jobs(monkeypatch):
    first_id = uuid4()
    second_id = uuid4()
    first_entered = Event()
    release_first = Event()
    second_entered = Event()
    finished = Event()
    order = []
    order_lock = Lock()

    def process_summaries(_session, analysis_id):
        with order_lock:
            order.append(analysis_id)
        if analysis_id == first_id:
            first_entered.set()
            assert release_first.wait(2)
        else:
            second_entered.set()
            finished.set()
        return SimpleNamespace(status="FAILED_ANALYSIS")

    monkeypatch.setattr(
        analysis_worker, "process_analysis_summaries", process_summaries
    )
    worker = analysis_worker.AnalysisWorker(FakeSession, concurrency=1)
    worker.start()
    try:
        worker.submit(first_id)
        worker.submit(second_id)
        assert first_entered.wait(1)
        assert not second_entered.wait(0.1)
        release_first.set()
        assert finished.wait(2)
        assert order == [first_id, second_id]
    finally:
        worker.stop()


def test_worker_coalesces_duplicate_queued_ids(monkeypatch):
    analysis_id = uuid4()
    processed = Event()
    calls = []

    def process_summaries(_session, current_id):
        calls.append(current_id)
        processed.set()
        return SimpleNamespace(status="FAILED_ANALYSIS")

    monkeypatch.setattr(
        analysis_worker, "process_analysis_summaries", process_summaries
    )
    worker = analysis_worker.AnalysisWorker(FakeSession, concurrency=1)
    worker.submit(analysis_id)
    worker.submit(analysis_id)
    worker.start()
    try:
        assert processed.wait(1)
    finally:
        worker.stop()

    assert calls == [analysis_id]


def test_worker_survives_failed_job(monkeypatch):
    failed_id = uuid4()
    successful_id = uuid4()
    completed = Event()

    def process_summaries(_session, analysis_id):
        if analysis_id == failed_id:
            raise RuntimeError("unexpected worker failure")
        completed.set()
        return SimpleNamespace(status="FAILED_ANALYSIS")

    monkeypatch.setattr(
        analysis_worker, "process_analysis_summaries", process_summaries
    )
    worker = analysis_worker.AnalysisWorker(FakeSession, concurrency=1)
    worker.start()
    try:
        worker.submit(failed_id)
        worker.submit(successful_id)
        assert completed.wait(2)
    finally:
        worker.stop()
