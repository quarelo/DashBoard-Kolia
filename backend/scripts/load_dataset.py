"""Import the meeting CSV and run every analysis, one at a time.

Built for an unattended run against a live backend + IA, from the repo root:

    make reunioes-plano        # only splits and validates the CSV; no login, no writes
    make reunioes LIMIT=5      # a short rehearsal: imports everything, analyses 5
    make reunioes              # the whole transcricoes_TOTVS.csv

It submits one analysis and waits for it to finish before submitting the next.
Firing all of them at once would only pile them into the IA's in-memory queue, where
progress is invisible and a restart loses the ordering; one at a time keeps every
completed meeting durable in the database, so re-running skips what is done.

The backend refuses an upload over 5 MiB or 1000 meetings, and
transcricoes_TOTVS.csv is 38 MiB and 1044 meetings, so a single upload of it could
never work. The CSV goes up in parts under both limits, each checked by the
backend's own parser before anything is sent. The split is deterministic: a re-run
sends the same bytes, and the backend answers 409 DUPLICATE_IMPORT, which is
expected here.

Credentials are KOLIA_EMAIL and KOLIA_PASSWORD, from the environment or from an env
file (`make` mounts the root .env read-only), so the password never reaches argv.

Safe to interrupt and re-run: parts already imported are refused as duplicates and
meetings already DONE are skipped.
"""
import argparse
import csv
import getpass
import io
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.meeting_parser import (  # noqa: E402
    MAX_IMPORT_BYTES,
    MAX_IMPORT_ROWS,
    ImportValidationError,
    parse_meeting_file,
)

POLL_SECONDS = 3
TERMINAL_OK = {"DONE"}
TERMINAL_BAD = {"FAILED", "FAILED_ANALYSIS", "DASHBOARD_READY_WITH_EMBEDDING_ERROR"}
# The HTTP body may carry 64 KiB of multipart envelope over MAX_IMPORT_BYTES;
# staying 256 KiB under the file limit keeps the envelope out of the question.
PART_MAX_BYTES = MAX_IMPORT_BYTES - 256 * 1024


def log(message: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {message}", flush=True)


def _read_csv(content: bytes) -> tuple[str, list[str], list[list[str]]]:
    text = content.decode("utf-8-sig")
    header_line = text.splitlines()[0] if text else ""
    # Same rule the backend uses to pick the delimiter.
    delimiter = ";" if header_line.count(";") > header_line.count(",") else ","
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
    header = next(reader, None)
    if not header:
        raise ValueError("o CSV não tem cabeçalho.")
    return delimiter, header, list(reader)


def _encode(rows: list[list[str]], delimiter: str) -> bytes:
    buffer = io.StringIO()
    csv.writer(buffer, delimiter=delimiter, lineterminator="\r\n").writerows(rows)
    return buffer.getvalue().encode("utf-8")


def csv_subset(content: bytes, external_ids: set[str]) -> bytes:
    """The same CSV with only the meetings in `external_ids`, header included."""
    delimiter, header, rows = _read_csv(content)
    names = [name.strip() for name in header]
    column = next((names.index(name) for name in ("ID_MEETING", "meeting_id") if name in names), None)
    if column is None:
        raise ValueError("o CSV não tem a coluna ID_MEETING.")
    return _encode([header] + [row for row in rows if row[column].strip() in external_ids], delimiter)


def csv_parts(
    content: bytes, max_bytes: int = PART_MAX_BYTES, max_rows: int = MAX_IMPORT_ROWS,
) -> list[tuple[bytes, int]]:
    """Split a meeting CSV into uploads the backend accepts: (bytes, meetings) each.

    Every part repeats the header and keeps the source's delimiter and row order,
    so the same CSV always yields the same parts.
    """
    delimiter, header, rows = _read_csv(content)

    def encode(rows: list[list[str]]) -> bytes:
        return _encode(rows, delimiter)

    head = encode([header])
    parts: list[tuple[bytes, int]] = []
    lines: list[bytes] = []
    size = len(head)
    for number, row in enumerate(rows, start=1):
        line = encode([row])
        if len(head) + len(line) > max_bytes:
            raise ValueError(f"a linha de dados {number} sozinha passa de {max_bytes} bytes.")
        if lines and (size + len(line) > max_bytes or len(lines) == max_rows):
            parts.append((head + b"".join(lines), len(lines)))
            lines, size = [], len(head)
        lines.append(line)
        size += len(line)
    if lines:
        parts.append((head + b"".join(lines), len(lines)))
    return parts


def credentials(env_file: str | None) -> tuple[str | None, str | None]:
    """KOLIA_EMAIL and KOLIA_PASSWORD: the environment first, then the env file."""
    values: dict[str, str] = {}
    if env_file and os.path.isfile(env_file):
        with open(env_file, encoding="utf-8-sig") as handle:
            for raw in handle:
                key, separator, value = raw.strip().partition("=")
                if separator and key in ("KOLIA_EMAIL", "KOLIA_PASSWORD"):
                    values[key] = value.strip().strip("\"'")
    return (
        os.environ.get("KOLIA_EMAIL") or values.get("KOLIA_EMAIL"),
        os.environ.get("KOLIA_PASSWORD") or values.get("KOLIA_PASSWORD"),
    )


def login(client: httpx.Client, email: str, password: str) -> str:
    response = client.post("/login", json={"email": email, "password": password})
    if response.status_code != 200:
        sys.exit(f"Login falhou ({response.status_code}): {response.text[:200]}")
    return response.json()["access_token"]


def _upload(client: httpx.Client, filename: str, content: bytes) -> tuple[int, dict]:
    response = client.post(
        "/api/imports", files={"file": (filename, content, "text/csv")}, timeout=120,
    )
    body = response.json() if response.content else {}
    if response.status_code == 201:
        return 201, body
    detail = body.get("detail", {}) if isinstance(body, dict) else {}
    if (response.status_code == 409 and isinstance(detail, dict)
            and detail.get("code") == "DUPLICATE_IMPORT"):
        return 409, body
    sys.exit(f"{filename}: importação falhou ({response.status_code}): {response.text[:300]}")


def import_parts(
    client: httpx.Client, parts: list[tuple[bytes, int]], part_ids: list[set[str]], stem: str,
) -> None:
    account_ids: set[str] | None = None
    for index, (part, _count) in enumerate(parts, start=1):
        label = f"Parte {index}/{len(parts)}"
        status, body = _upload(client, f"{stem}_parte_{index:02d}.csv", part)
        if status == 201:
            log(f"{label}: importadas {body['imported_count']}, versionadas "
                f"{body.get('versioned_count', 0)}, ignoradas {body['skipped_count']}.")
            continue
        # The backend refuses a file it has a record of, even when meetings of that
        # file were deleted since. On 2026-09-12 part 01 kept its record because two
        # of its meetings kept their analysis, and its other 130 were deleted: without
        # this, a re-run would never bring them back. Different bytes pass.
        if account_ids is None:
            account_ids = {meeting["external_id"] for meeting in all_meetings(client)}
        missing = part_ids[index - 1] - account_ids
        if not missing:
            log(f"{label}: já importada antes; seguindo.")
            continue
        status, body = _upload(
            client, f"{stem}_parte_{index:02d}_faltantes.csv", csv_subset(part, missing))
        if status == 201:
            log(f"{label}: já importada antes, mas faltavam {len(missing)} reuniões na "
                f"conta; reenviadas {body['imported_count']}.")
        else:
            log(f"{label}: as {len(missing)} reuniões que faltavam também foram recusadas "
                "como duplicadas; seguindo.")


def meetings_to_analyse(meetings: list[dict], csv_ids: set[str]) -> list[dict]:
    """Meetings of this CSV that have no analysis yet.

    The account can hold meetings from other imports. On 2026-09-12 it had 454 from
    an older ds.csv next to the 1044 of transcricoes_TOTVS.csv, and the rehearsal
    analysed five of those, because anything without an analysis was taken.
    """
    return [meeting for meeting in meetings
            if meeting.get("analysis_id") is None and meeting.get("external_id") in csv_ids]


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
    parser.add_argument("--csv", default="transcricoes_TOTVS.csv")
    parser.add_argument("--email", default=None, help="Padrão: KOLIA_EMAIL.")
    parser.add_argument("--env-file", default="/run/kolia.env",
                        help="Arquivo com KOLIA_EMAIL e KOLIA_PASSWORD, se não vierem do ambiente.")
    parser.add_argument("--backend", default="http://localhost:8080")
    # A single 2000-token chunk takes about 70s on the reference host, so this is
    # several chunks' worth of silence before calling an analysis stuck.
    parser.add_argument("--stall", type=float, default=600, metavar="SEGUNDOS",
                        help="Desiste de uma análise após este tempo SEM progresso.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Processa só as N primeiras — use para um ensaio curto.")
    # A batch that fails from the first meeting is a broken service or a bad
    # secret, not bad luck: without this it would spend hours logging the same
    # error 500 times, each one waiting out the stall window.
    parser.add_argument("--abort-after", type=int, default=5, metavar="N",
                        help="Aborta após N falhas consecutivas.")
    parser.add_argument("--skip-import", action="store_true")
    parser.add_argument("--dry-run", action="store_true",
                        help="Só divide e valida o CSV; não faz login nem grava nada.")
    args = parser.parse_args()

    if not os.path.exists(args.csv):
        sys.exit(f"CSV não encontrado: {args.csv}")
    with open(args.csv, "rb") as handle:
        content = handle.read()
    csv_ids: set[str] = set()
    part_ids: list[set[str]] = []
    try:
        parts = csv_parts(content)
        # The backend's own parser, before any write: a part it would refuse stops
        # the batch here instead of halfway through the upload.
        for index, (part, count) in enumerate(parts, start=1):
            parsed = parse_meeting_file(part, "parte.csv")
            if len(parsed.meetings) != count:
                raise ValueError(f"a parte {index} leu {len(parsed.meetings)} de {count} reuniões.")
            part_ids.append({meeting.external_id for meeting in parsed.meetings})
            csv_ids.update(part_ids[-1])
    except (ValueError, csv.Error, ImportValidationError) as error:
        sys.exit(f"CSV inválido: {error}")
    total_rows = sum(count for _part, count in parts)
    log(f"{args.csv}: {total_rows} reuniões em {len(parts)} partes de até "
        f"{PART_MAX_BYTES / 2**20:.2f} MiB, todas aceitas pelo parser do backend.")
    if args.dry_run:
        for index, (part, count) in enumerate(parts, start=1):
            log(f"Parte {index}: {count} reuniões, {len(part) / 2**20:.2f} MiB.")
        return

    email, password = credentials(args.env_file)
    email = args.email or email
    if not email:
        sys.exit("Defina KOLIA_EMAIL no .env ou passe --email.")
    password = password or getpass.getpass("Senha: ")

    with httpx.Client(base_url=args.backend, timeout=60) as client:
        client.headers["Authorization"] = f"Bearer {login(client, email, password)}"
        if not args.skip_import:
            import_parts(client, parts, part_ids, Path(args.csv).stem)

        meetings = all_meetings(client)
        from_csv = sum(1 for meeting in meetings if meeting.get("external_id") in csv_ids)
        pending = meetings_to_analyse(meetings, csv_ids)
        log(f"{len(meetings)} reuniões na conta; {from_csv} deste CSV, "
            f"{len(pending)} delas sem análise. As de outros imports ficam de fora.")
        without_analysis = len(pending)
        if args.limit:
            pending = pending[:args.limit]
        if not pending:
            log("Nenhuma reunião para analisar.")
            return
        limited = (f" (--limit {args.limit}; {without_analysis} sem análise no total)"
                   if len(pending) < without_analysis else "")
        log(f"Vão ser analisadas {len(pending)} reuniões{limited}.")

        done = failed = streak = 0
        durations: list[float] = []
        started = time.monotonic()
        for index, meeting in enumerate(pending, start=1):
            began = time.monotonic()
            response = client.post(f"/api/meetings/{meeting['id']}/analysis")
            if response.status_code not in (200, 202):
                failed += 1
                streak += 1
                log(f"[{index}/{len(pending)}] {meeting['external_id']}: envio falhou "
                    f"({response.status_code}) {response.text[:160]}")
                if streak >= args.abort_after:
                    log(f"Abortado: {streak} falhas seguidas. Nada foi processado "
                        "desde então; corrija a causa e rode de novo — as concluídas "
                        "são ignoradas.")
                    break
                continue
            status = wait_for(client, meeting["id"], args.stall)
            elapsed = time.monotonic() - began
            if status in TERMINAL_OK:
                done += 1
                streak = 0
                # Only successful runs shape the average: a stalled one contributes
                # the whole --stall window and would push the estimate up for the
                # rest of the batch, which is the opposite of what it is for.
                durations.append(elapsed)
            else:
                failed += 1
                streak += 1
                if streak >= args.abort_after:
                    log(f"Abortado: {streak} análises seguidas terminaram em falha. "
                        "Corrija a causa e rode de novo.")
                    break
            average = sum(durations) / len(durations) if durations else elapsed
            remaining = timedelta(seconds=int(average * (len(pending) - index)))
            log(f"[{index}/{len(pending)}] {meeting['external_id']}: {status} "
                f"em {elapsed:.0f}s | média {average:.0f}s | ok={done} falhas={failed} "
                f"| restam ~{remaining}")

        total = timedelta(seconds=int(time.monotonic() - started))
        average = f"{sum(durations) / len(durations):.0f}s" if durations else "sem concluídas"
        log(f"Fim: {done} concluídas, {failed} com falha, em {total}; "
            f"tempo médio por reunião: {average}.")
        if failed:
            log("Rode de novo para tentar as que falharam; as concluídas são ignoradas.")


if __name__ == "__main__":
    main()
