"""Import the meeting CSV and run every analysis, one at a time.

Built for an unattended overnight run against a live backend + IA:

    python scripts/load_dataset.py --csv ../ia/dataset_tratado_revisado.csv \
        --email ana@empresa.com

It submits one analysis and waits for it to finish before submitting the next.
Firing all 500 at once would only pile them into the IA's in-memory queue, where
progress is invisible and a restart loses the ordering; one at a time keeps every
completed meeting durable in the database, so re-running skips what is done.

Safe to interrupt and re-run: import is idempotent (duplicate uploads are refused
by the backend, which is not an error here) and meetings already DONE are skipped.
"""
import argparse
import getpass
import itertools
import os
import sys
import time
from datetime import datetime, timedelta

import httpx

POLL_SECONDS = 3
TERMINAL_OK = {"DONE"}
TERMINAL_BAD = {"FAILED", "FAILED_ANALYSIS", "DASHBOARD_READY_WITH_EMBEDDING_ERROR"}


def log(message: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {message}", flush=True)


def login(client: httpx.Client, email: str, password: str) -> str:
    response = client.post("/login", json={"email": email, "password": password})
    if response.status_code != 200:
        sys.exit(f"Login falhou ({response.status_code}): {response.text[:200]}")
    return response.json()["access_token"]


def import_csv(client: httpx.Client, csv_path: str) -> None:
    with open(csv_path, "rb") as handle:
        response = client.post(
            "/api/imports", files={"file": (os.path.basename(csv_path), handle)},
            timeout=120,
        )
    if response.status_code == 201:
        body = response.json()
        log(f"Importadas {body['imported_count']}, versionadas "
            f"{body.get('versioned_count', 0)}, ignoradas {body['skipped_count']}.")
        return
    detail = response.json().get("detail", {})
    if response.status_code == 409 and detail.get("code") == "DUPLICATE_IMPORT":
        # Expected on a re-run: the meetings are already in the database.
        log("CSV já importado antes; seguindo para as análises.")
        return
    sys.exit(f"Importação falhou ({response.status_code}): {response.text[:300]}")


def all_meetings(client: httpx.Client) -> list[dict]:
    meetings, offset = [], 0
    while True:
        page = client.get("/api/meetings",
                          params={"offset": offset, "limit": 100}).json()
        meetings.extend(page["items"])
        offset += len(page["items"])
        if offset >= page["total"] or not page["items"]:
            return meetings


def wait_for(client: httpx.Client, meeting_id: str, stall_seconds: float) -> str:
    """Poll one analysis to a terminal state; returns the status it settled on.

    Gives up on lack of progress, not on elapsed time. A total budget gets both
    cases wrong: a healthy 21-chunk meeting takes ~20 minutes and was being marked
    failed at 15, while a genuinely stuck one would still hold the batch for the
    whole budget. Progress is chunks summarised plus embeddings written, so an
    analysis that is still moving is never abandoned however long it takes.
    """
    last_progress = time.monotonic()
    seen = None
    while True:
        response = client.get(f"/api/meetings/{meeting_id}/analysis")
        if response.status_code != 200:
            return f"HTTP {response.status_code}"
        body = response.json()
        status = body.get("status", "?")
        if status in TERMINAL_OK or status in TERMINAL_BAD:
            return status
        progress = (status,
                    body.get("processed_chunks"),
                    body.get("embedding_progress_percent"))
        if progress != seen:
            seen, last_progress = progress, time.monotonic()
        elif time.monotonic() - last_progress > stall_seconds:
            return "TRAVADA"
        time.sleep(POLL_SECONDS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Carrega o dataset e roda as análises.")
    parser.add_argument("--csv", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--backend", default="http://localhost:8080")
    # A single 2000-token chunk takes about 70s on the reference host, so this is
    # several chunks' worth of silence before calling an analysis stuck.
    parser.add_argument("--stall", type=float, default=600, metavar="SEGUNDOS",
                        help="Desiste de uma análise após este tempo SEM progresso.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Processa só as N primeiras — use para um ensaio curto.")
    parser.add_argument("--skip-import", action="store_true")
    args = parser.parse_args()

    if not os.path.exists(args.csv):
        sys.exit(f"CSV não encontrado: {args.csv}")
    password = os.environ.get("KOLIA_PASSWORD") or getpass.getpass("Senha: ")

    with httpx.Client(base_url=args.backend, timeout=60) as client:
        client.headers["Authorization"] = f"Bearer {login(client, args.email, password)}"
        if not args.skip_import:
            import_csv(client, args.csv)

        meetings = all_meetings(client)
        pending = [m for m in meetings if m.get("analysis_id") is None]
        log(f"{len(meetings)} reuniões no banco; {len(pending)} sem análise.")
        if args.limit:
            pending = pending[:args.limit]

        done = failed = 0
        durations: list[float] = []
        started = time.monotonic()
        for index, meeting in enumerate(pending, start=1):
            began = time.monotonic()
            response = client.post(f"/api/meetings/{meeting['id']}/analysis")
            if response.status_code not in (200, 202):
                failed += 1
                log(f"[{index}/{len(pending)}] {meeting['external_id']}: envio falhou "
                    f"({response.status_code}) {response.text[:120]}")
                continue
            status = wait_for(client, meeting["id"], args.stall)
            elapsed = time.monotonic() - began
            durations.append(elapsed)
            if status in TERMINAL_OK:
                done += 1
            else:
                failed += 1
            # Median beats mean here: one stuck analysis should not distort the ETA.
            ordered = sorted(durations)
            median = ordered[len(ordered) // 2]
            remaining = timedelta(seconds=int(median * (len(pending) - index)))
            log(f"[{index}/{len(pending)}] {meeting['external_id']}: {status} "
                f"em {elapsed:.0f}s | ok={done} falhas={failed} | restam ~{remaining}")

        total = timedelta(seconds=int(time.monotonic() - started))
        log(f"Fim: {done} concluídas, {failed} com falha, em {total}.")
        if failed:
            log("Rode de novo para tentar as que falharam; as concluídas são ignoradas.")


if __name__ == "__main__":
    main()
