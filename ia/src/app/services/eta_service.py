"""Estimated time to finish an analysis, calibrated from this host's own history.

Analysis cost is not proportional to chunks alone: every run pays a fixed price
(model load, embedding call, consolidation) on top of per-chunk work, so a single
"seconds per chunk" number is wrong at both ends.

A global straight line is wrong too. Real history on the reference machine is not
monotonic — 48-chunk runs averaged ~1392s while 22-chunk runs averaged ~1518s —
and least squares over that lifts the intercept to ~205s, which then predicts
~232s for a 1-chunk run that actually takes ~32s. A 7x error, and precisely at the
size a bulk CSV import uses.

So we prefer local evidence: group finished runs by chunk count, take each group's
median, and answer an exact size from its own group, an in-range size by
interpolating its neighbours. The least-squares line is kept only to extrapolate
past the observed range, and configured defaults cover having no history at all.

Estimates are advisory. They describe what this host did recently, so they drift
after a model, hardware or concurrency change, and they say nothing about a run
that is going to fail.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.app.core.config import settings
from src.app.models.analysis import MeetingAnalysis

# History older than this is more misleading than helpful after a config change.
MAX_SAMPLES = 200
# A row whose updated_at drifted long after the run (observed: 44h on a 0-chunk
# row) would dominate a least-squares fit, so samples are bounded on both sides.
MIN_SAMPLE_SECONDS = 0.5
MAX_SAMPLE_SECONDS = 6 * 60 * 60

TERMINAL_STATUSES = ("DONE", "DASHBOARD_READY_WITH_EMBEDDING_ERROR")
PENDING_STATUSES = ("PENDING", "PROCESSING", "ANALYZING", "DASHBOARD_READY", "EMBEDDING")


@dataclass(frozen=True)
class Calibration:
    """How long a run of `chunks` chunks is expected to take, and how sure we are.

    `by_size` maps an observed chunk count to the median duration measured for it.
    It is consulted before the fitted line, so a size we have actually run is
    answered with its own evidence instead of a global trend.
    """

    overhead_seconds: float
    seconds_per_chunk: float
    sample_count: int
    measured: bool
    by_size: dict[int, float] = field(default_factory=dict)

    def _extrapolate(self, chunks: int) -> float:
        return max(self.overhead_seconds + self.seconds_per_chunk * chunks, 0.0)

    def seconds_for(self, chunks: int) -> float:
        chunks = max(chunks, 1)
        if not self.by_size:
            return self._extrapolate(chunks)
        if chunks in self.by_size:
            return self.by_size[chunks]
        sizes = sorted(self.by_size)
        below = [s for s in sizes if s < chunks]
        above = [s for s in sizes if s > chunks]
        if not below or not above:
            # Outside everything we have measured; the trend line is all we have.
            return self._extrapolate(chunks)
        low, high = below[-1], above[0]
        low_seconds, high_seconds = self.by_size[low], self.by_size[high]
        weight = (chunks - low) / (high - low)
        return low_seconds + weight * (high_seconds - low_seconds)


def _default_calibration(sample_count: int = 0) -> Calibration:
    return Calibration(
        overhead_seconds=settings.eta_default_overhead_seconds,
        seconds_per_chunk=settings.eta_default_seconds_per_chunk,
        sample_count=sample_count,
        measured=False,
    )


def _samples(db: Session) -> list[tuple[int, float]]:
    rows = db.execute(
        select(MeetingAnalysis.total_chunks,
               MeetingAnalysis.created_at, MeetingAnalysis.updated_at)
        .where(MeetingAnalysis.status.in_(TERMINAL_STATUSES),
               MeetingAnalysis.total_chunks > 0)
        .order_by(MeetingAnalysis.created_at.desc())
        .limit(MAX_SAMPLES)
    ).all()
    samples = []
    for chunks, created_at, updated_at in rows:
        if created_at is None or updated_at is None:
            continue
        seconds = (updated_at - created_at).total_seconds()
        if MIN_SAMPLE_SECONDS <= seconds <= MAX_SAMPLE_SECONDS:
            samples.append((chunks, seconds))
    return samples


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def calibrate(db: Session) -> Calibration:
    """Median duration per observed size, plus a trend line for sizes beyond them."""
    samples = _samples(db)
    if not samples:
        return _default_calibration()

    grouped: dict[int, list[float]] = {}
    for chunks, seconds in samples:
        grouped.setdefault(chunks, []).append(seconds)
    # Median per size resists the wide spread real runs show at the same size
    # (observed: 772s to 1984s across six 48-chunk runs).
    by_size = {chunks: _median(values) for chunks, values in grouped.items()}

    fallback = _default_calibration()
    overhead, rate = fallback.overhead_seconds, fallback.seconds_per_chunk
    if len(by_size) >= 2:
        points = sorted(by_size.items())
        n = len(points)
        mean_x = sum(c for c, _ in points) / n
        mean_y = sum(s for _, s in points) / n
        variance = sum((c - mean_x) ** 2 for c, _ in points)
        covariance = sum((c - mean_x) * (s - mean_y) for c, s in points)
        if variance:
            fitted_rate = covariance / variance
            fitted_overhead = mean_y - fitted_rate * mean_x
            # Keep the fit only when it is physical; otherwise the seeded defaults
            # extrapolate more sensibly than a downward-sloping line would.
            if fitted_rate > 0 and fitted_overhead >= 0:
                overhead, rate = fitted_overhead, fitted_rate
    return Calibration(overhead, rate, len(samples), True, by_size)


def _elapsed(analysis: MeetingAnalysis) -> float:
    """How long a still-running analysis has been going, measured against now.

    Only meaningful while the analysis is pending: `remaining = total -
    _elapsed(...)` needs "how long has it been running so far", which can only
    be answered against the current moment. A finished analysis needs
    `_duration` instead — see its docstring for why the two must not be
    conflated.
    """
    started = analysis.created_at
    if started is None:
        return 0.0
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return max((datetime.now(timezone.utc) - started).total_seconds(), 0.0)


def _duration(analysis: MeetingAnalysis) -> float:
    """How long a finished analysis actually took, frozen at completion.

    `updated_at` stops moving once the row stops changing, so this is exactly
    the measurement `_samples` already uses for calibration. Using `_elapsed`
    (now - created_at) here instead would report a number that keeps growing
    the longer someone waits before asking — a analysis that took 8 minutes
    would read as "94 minutes elapsed" if queried an hour and a half after it
    finished, which is what an analysis queried well after completion showed
    before this fix.
    """
    started, finished = analysis.created_at, analysis.updated_at
    if started is None or finished is None:
        return _elapsed(analysis)
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    if finished.tzinfo is None:
        finished = finished.replace(tzinfo=timezone.utc)
    return max((finished - started).total_seconds(), 0.0)


def estimate_analysis(db: Session, analysis: MeetingAnalysis,
                      calibration: Calibration | None = None) -> dict:
    """Remaining seconds for one analysis, or None once it is no longer running."""
    calibration = calibration or calibrate(db)
    if analysis.status not in PENDING_STATUSES:
        return {"estimated_seconds_remaining": None, "estimated_total_seconds": None,
                "elapsed_seconds": round(_duration(analysis), 1),
                "calibration": describe(calibration)}
    total = calibration.seconds_for(analysis.total_chunks)
    remaining = total - _elapsed(analysis)
    return {
        # A run past its estimate is not finished; report a floor, not a negative.
        "estimated_seconds_remaining": round(max(remaining, 0.0), 1),
        "estimated_total_seconds": round(total, 1),
        "elapsed_seconds": round(_elapsed(analysis), 1),
        "calibration": describe(calibration),
    }


def estimate_backlog(db: Session, concurrency: int | None = None) -> dict:
    """Queue-wide view: what is still pending and roughly how long it needs.

    The worker queue lives in memory, so the durable question "what is unfinished"
    is answered from the analyses table, which also survives a restart.
    """
    calibration = calibrate(db)
    concurrency = max(concurrency or settings.analysis_worker_concurrency, 1)
    rows = db.execute(
        select(MeetingAnalysis.status, MeetingAnalysis.total_chunks,
               MeetingAnalysis.created_at)
        .where(MeetingAnalysis.status.in_(PENDING_STATUSES))
        .order_by(MeetingAnalysis.created_at.asc())
    ).all()
    serial_seconds = 0.0
    for _status, chunks, _created_at in rows:
        serial_seconds += calibration.seconds_for(chunks)
    return {
        "pending_analyses": len(rows),
        "pending_chunks": sum(chunks for _s, chunks, _c in rows),
        "worker_concurrency": concurrency,
        # Wall clock assumes the workers stay busy; Ollama itself serialises when
        # OLLAMA_NUM_PARALLEL is 1, so raising concurrency alone may not help.
        "estimated_seconds_remaining": round(serial_seconds / concurrency, 1),
        "estimated_serial_seconds": round(serial_seconds, 1),
        "calibration": describe(calibration),
    }


def estimate_batch(db: Session, analyses: int, chunks_each: int = 1,
                   concurrency: int | None = None) -> dict:
    """What a not-yet-submitted batch would cost — e.g. importing a whole CSV."""
    calibration = calibrate(db)
    concurrency = max(concurrency or settings.analysis_worker_concurrency, 1)
    serial_seconds = analyses * calibration.seconds_for(chunks_each)
    return {
        "analyses": analyses,
        "chunks_each": chunks_each,
        "worker_concurrency": concurrency,
        "estimated_seconds": round(serial_seconds / concurrency, 1),
        "estimated_serial_seconds": round(serial_seconds, 1),
        "calibration": describe(calibration),
    }


def describe(calibration: Calibration) -> dict:
    return {
        "overhead_seconds": round(calibration.overhead_seconds, 1),
        "seconds_per_chunk": round(calibration.seconds_per_chunk, 1),
        "sample_count": calibration.sample_count,
        # False means nobody has finished an analysis here yet: the numbers are
        # configured guesses, not measurements of this host.
        "measured": calibration.measured,
    }
