import argparse
import ast
import json
from pathlib import Path
from time import perf_counter, sleep
from urllib.request import Request, urlopen


def extract_payload(path: Path) -> dict:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "payload"
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise ValueError("payload não encontrado")


def request_json(url: str, *, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="http://localhost:3000")
    parser.add_argument("--timeout", type=float, default=1800)
    args = parser.parse_args()

    payload = extract_payload(args.input)
    started = perf_counter()
    accepted = request_json(f"{args.base_url}/analisar", payload=payload)
    accepted_seconds = perf_counter() - started
    analysis_id = accepted["analysis_id"]
    partial_seconds = None
    complete_seconds = None
    snapshots = []
    final = accepted

    while perf_counter() - started < args.timeout:
        final = request_json(f"{args.base_url}/analises/{analysis_id}")
        elapsed = perf_counter() - started
        snapshots.append({
            "seconds": round(elapsed, 3),
            "status": final["status"],
            "summary_stage": final["summary_stage"],
            "summary_progress_percent": final["summary_progress_percent"],
            "embedding_progress_percent": final["embedding_progress_percent"],
        })
        if partial_seconds is None and final["processed_chunks"] >= min(6, final["total_chunks"]):
            partial_seconds = elapsed
        if complete_seconds is None and final["summary_is_final"]:
            complete_seconds = elapsed
        if final["status"] in {"DONE", "FAILED", "FAILED_ANALYSIS", "DASHBOARD_READY_WITH_EMBEDDING_ERROR"}:
            break
        sleep(2)

    report = {
        "analysis_id": analysis_id,
        "accepted_seconds": round(accepted_seconds, 3),
        "partial_seconds": round(partial_seconds, 3) if partial_seconds else None,
        "complete_summary_seconds": round(complete_seconds, 3) if complete_seconds else None,
        "total_seconds": round(perf_counter() - started, 3),
        "snapshots": snapshots,
        "accepted_response": accepted,
        "final_response": final,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
