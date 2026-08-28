import logging
from queue import Queue
from threading import Lock, Thread
from uuid import UUID

from sqlalchemy import select

from src.app.models.analysis import MeetingAnalysis
from src.app.services.analysis_service import (
    process_analysis_embeddings,
    process_analysis_summaries,
)

logger = logging.getLogger("uvicorn.error")

_STOP = object()
_RECOVERABLE_STATUSES = (
    "PROCESSING",
    "ANALYZING",
    "DASHBOARD_READY",
    "EMBEDDING",
)


def is_recoverable_status(status: str) -> bool:
    return status in _RECOVERABLE_STATUSES


class AnalysisWorker:
    def __init__(self, session_factory, concurrency: int = 1):
        if concurrency < 1:
            raise ValueError("A concorrência do worker precisa ser pelo menos 1.")
        self._session_factory = session_factory
        self._concurrency = concurrency
        self._queue: Queue = Queue()
        self._queued_ids: set[UUID] = set()
        self._lock = Lock()
        self._threads: list[Thread] = []
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        for index in range(self._concurrency):
            thread = Thread(
                target=self._run,
                name=f"analysis-worker-{index + 1}",
                daemon=True,
            )
            thread.start()
            self._threads.append(thread)

    def submit(self, analysis_id: UUID) -> None:
        with self._lock:
            if analysis_id in self._queued_ids:
                return
            self._queued_ids.add(analysis_id)
        self._queue.put(analysis_id)

    def recover(self) -> None:
        session = self._session_factory()
        try:
            statement = select(MeetingAnalysis.id).where(
                MeetingAnalysis.status.in_(_RECOVERABLE_STATUSES)
            )
            for analysis_id in session.execute(statement).scalars().all():
                self.submit(analysis_id)
        finally:
            session.close()

    def stop(self) -> None:
        if not self._started:
            return
        for _thread in self._threads:
            self._queue.put(_STOP)
        for thread in self._threads:
            thread.join(timeout=5)
        self._threads.clear()
        self._started = False

    def _run(self) -> None:
        while True:
            analysis_id = self._queue.get()
            if analysis_id is _STOP:
                self._queue.task_done()
                return
            session = self._session_factory()
            try:
                analysis = session.get(MeetingAnalysis, analysis_id)
                if analysis is None:
                    continue
                if not getattr(analysis, "summary_is_final", False):
                    analysis = process_analysis_summaries(session, analysis_id)
                if analysis.status in {
                    "DASHBOARD_READY",
                    "EMBEDDING",
                    "DASHBOARD_READY_WITH_EMBEDDING_ERROR",
                }:
                    process_analysis_embeddings(session, analysis_id)
            except Exception:
                logger.exception("analysis_id=%s worker_failed", analysis_id)
            finally:
                session.close()
                with self._lock:
                    self._queued_ids.discard(analysis_id)
                self._queue.task_done()
