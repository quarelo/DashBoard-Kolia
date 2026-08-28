import argparse
import ast
import json
import resource
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

import httpx

from src.app.core.config import settings
from src.app.services.analysis_service import build_compact_final_summary
from src.app.services.chunk_service import (
    clean_transcription,
    sanitize_transcription,
    select_relevant_transcription,
)
from src.app.services.llm_service import consolidate_summaries, generate_chunk_summary
from src.app.services.token_service import count_tokens, split_text_by_tokens


REQUIRED_FIELDS = {
    "resumo_geral",
    "temas_agrupados",
    "problemas_identificados",
    "decisoes_tomadas",
    "duvidas_em_aberto",
    "oportunidades_insights",
    "evidencias_importantes",
    "metricas_negocio",
    "acoes_recomendadas",
}

VARIANTS = {
    "full-llama3.2-1b": {
        "chunk_model": "llama3.2:1b", "consolidation_model": "llama3.2:1b",
        "clean": True, "overlap": 0,
        "chunk_think": False, "chunk_predict": 192,
        "consolidation_think": False, "consolidation_predict": 384,
        "concurrency": 1, "deterministic_final": True,
    },
    "full-gemma3-1b": {
        "chunk_model": "gemma3:1b", "consolidation_model": "gemma3:1b",
        "clean": True, "overlap": 0,
        "chunk_think": False, "chunk_predict": 192,
        "consolidation_think": False, "consolidation_predict": 384,
        "concurrency": 1, "deterministic_final": True,
    },
    "full-gemma3-1b-ai-final": {
        "chunk_model": "gemma3:1b", "consolidation_model": "gemma3:1b",
        "clean": True, "overlap": 0,
        "chunk_think": False, "chunk_predict": 192,
        "consolidation_think": False, "consolidation_predict": 768,
        "concurrency": 1, "deterministic_final": False,
    },
    "fast-retention-05": {
        "chunk_model": "qwen3:1.7b", "consolidation_model": "qwen3:1.7b",
        "clean": True, "retention": 0.05, "overlap": 0,
        "chunk_think": False, "chunk_predict": 192,
        "consolidation_think": False, "consolidation_predict": 384,
        "concurrency": 1, "deterministic_final": True,
    },
    "fast-retention-10": {
        "chunk_model": "qwen3:1.7b", "consolidation_model": "qwen3:1.7b",
        "clean": True, "retention": 0.10, "overlap": 0,
        "chunk_think": False, "chunk_predict": 128,
        "consolidation_think": False, "consolidation_predict": 384,
        "concurrency": 1, "deterministic_final": True,
    },
    "fast-retention-15": {
        "chunk_model": "qwen3:1.7b", "consolidation_model": "qwen3:1.7b",
        "clean": True, "retention": 0.15, "overlap": 0,
        "chunk_think": False, "chunk_predict": 192,
        "consolidation_think": False, "consolidation_predict": 768,
        "concurrency": 1,
    },
    "fast-retention-25": {
        "chunk_model": "qwen3:1.7b", "consolidation_model": "qwen3:1.7b",
        "clean": True, "retention": 0.25, "overlap": 0,
        "chunk_think": False, "chunk_predict": 192,
        "consolidation_think": False, "consolidation_predict": 768,
        "concurrency": 1,
    },
    "fast-retention-35": {
        "chunk_model": "qwen3:1.7b", "consolidation_model": "qwen3:1.7b",
        "clean": True, "retention": 0.35, "overlap": 0,
        "chunk_think": False, "chunk_predict": 192,
        "consolidation_think": False, "consolidation_predict": 768,
        "concurrency": 1,
    },
    "hybrid-local-0.6b-1.7b": {
        "chunk_model": "qwen3:0.6b", "consolidation_model": "qwen3:1.7b",
        "clean": True, "overlap": 0, "chunk_think": False,
        "chunk_predict": 192, "consolidation_think": False,
        "consolidation_predict": 768, "concurrency": 1,
    },
    "optimized-local-1.7b": {
        "chunk_model": "qwen3:1.7b", "consolidation_model": "qwen3:1.7b",
        "clean": True, "overlap": 0, "chunk_think": False,
        "chunk_predict": 192, "consolidation_think": False,
        "consolidation_predict": 768, "concurrency": 1,
    },
    "optimized-local-parallel-2": {
        "chunk_model": "qwen3:1.7b", "consolidation_model": "qwen3:1.7b",
        "clean": True, "overlap": 0, "chunk_think": False,
        "chunk_predict": 192, "consolidation_think": False,
        "consolidation_predict": 768, "concurrency": 2,
    },
    "optimized-gemma3-parallel-2": {
        "chunk_model": "gemma3:1b", "consolidation_model": "gemma3:1b",
        "clean": True, "overlap": 0, "chunk_think": False,
        "chunk_predict": 192, "consolidation_think": False,
        "consolidation_predict": 768, "concurrency": 2,
        "deterministic_final": True,
    },
    "baseline-3b": {
        "chunk_model": "qwen2.5:3b", "consolidation_model": "qwen2.5:3b",
        "clean": False, "overlap": 200, "chunk_think": True,
        "chunk_predict": 768, "consolidation_think": True,
        "consolidation_predict": 1024, "concurrency": 1,
    },
    "optimized-3b": {
        "chunk_model": "qwen2.5:3b", "consolidation_model": "qwen2.5:3b",
        "clean": True, "overlap": 0, "chunk_think": False,
        "chunk_predict": 384, "consolidation_think": False,
        "consolidation_predict": 768, "concurrency": 1,
    },
    "hybrid-1.5b-3b": {
        "chunk_model": "qwen2.5:1.5b", "consolidation_model": "qwen2.5:3b",
        "clean": True, "overlap": 0, "chunk_think": False,
        "chunk_predict": 384, "consolidation_think": False,
        "consolidation_predict": 768, "concurrency": 1,
    },
    "hybrid-parallel-2": {
        "chunk_model": "qwen2.5:1.5b", "consolidation_model": "qwen2.5:3b",
        "clean": True, "overlap": 0, "chunk_think": False,
        "chunk_predict": 384, "consolidation_think": False,
        "consolidation_predict": 768, "concurrency": 2,
    },
}


def prepare_variant_text(transcription: str, variant: dict) -> str:
    if not variant.get("clean"):
        return sanitize_transcription(transcription)
    retention = variant.get("retention")
    if retention is not None:
        return select_relevant_transcription(transcription, retention)
    return clean_transcription(transcription)


def build_variant_report(
    *, name, original_tokens, clean_tokens, chunks, preparation_seconds,
    chunk_seconds, consolidation_seconds, peak_rss_mb, summary, error,
    chunk_summaries=None,
):
    critical_path = preparation_seconds + sum(chunk_seconds) + consolidation_seconds
    coverage = len(REQUIRED_FIELDS.intersection(summary or {})) / len(REQUIRED_FIELDS)
    return {
        "variant": name,
        "original_tokens": original_tokens,
        "clean_tokens": clean_tokens,
        "token_reduction_ratio": round(
            1 - (clean_tokens / original_tokens), 4
        ) if original_tokens else 0.0,
        "chunks": chunks,
        "preparation_seconds": round(preparation_seconds, 3),
        "chunk_seconds": [round(value, 3) for value in chunk_seconds],
        "consolidation_seconds": round(consolidation_seconds, 3),
        "critical_path_seconds": round(critical_path, 3),
        "peak_rss_mb": round(peak_rss_mb, 1),
        "required_field_coverage": coverage,
        "meets_300_seconds": not error and critical_path <= 300,
        "error": error,
        "chunk_summaries": chunk_summaries or [],
        "summary": summary,
    }


def extract_transcription(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "payload" for target in node.targets
        ):
            payload = ast.literal_eval(node.value)
            return str(payload["transcription"])
    raise ValueError(f"payload com transcription não encontrado em {path}")


def _peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def _preload(model: str) -> None:
    httpx.post(
        settings.ollama_generate_url,
        json={"model": model, "prompt": "", "keep_alive": settings.ollama_keep_alive},
        timeout=settings.ollama_generate_timeout_seconds,
    ).raise_for_status()


def run_variant(name: str, transcription: str, max_chunks: int | None = None) -> dict:
    variant = VARIANTS[name]
    original = sanitize_transcription(transcription)
    started = perf_counter()
    prepared = prepare_variant_text(original, variant)
    chunks = split_text_by_tokens(
        prepared, settings.max_tokens_per_chunk, variant["overlap"]
    )
    if max_chunks is not None:
        chunks = chunks[:max_chunks]
    preparation_seconds = perf_counter() - started
    previous = {
        key: getattr(settings, key)
        for key in (
            "chunk_model", "consolidation_model", "ollama_chunk_think",
            "ollama_chunk_num_predict", "ollama_consolidation_think",
            "ollama_consolidation_num_predict",
        )
    }
    settings.chunk_model = variant["chunk_model"]
    settings.consolidation_model = variant["consolidation_model"]
    settings.ollama_chunk_think = variant["chunk_think"]
    settings.ollama_chunk_num_predict = variant["chunk_predict"]
    settings.ollama_consolidation_think = variant["consolidation_think"]
    settings.ollama_consolidation_num_predict = variant["consolidation_predict"]
    chunk_seconds = []
    summary = None
    summaries = []
    error = None
    wall_started = perf_counter()

    def summarize(chunk):
        item_started = perf_counter()
        value = generate_chunk_summary(chunk)
        return value, perf_counter() - item_started

    try:
        _preload(variant["chunk_model"])
        if variant["concurrency"] == 2:
            with ThreadPoolExecutor(max_workers=2) as executor:
                generated = list(executor.map(summarize, chunks))
        else:
            generated = []
            for chunk in chunks:
                generated.append(summarize(chunk))
        summaries = [item[0] for item in generated]
        chunk_seconds = [item[1] for item in generated]
        consolidation_started = perf_counter()
        if variant.get("deterministic_final"):
            summary = build_compact_final_summary(summaries)
        else:
            _preload(variant["consolidation_model"])
            summary = consolidate_summaries(summaries)
        consolidation_seconds = perf_counter() - consolidation_started
    except Exception as exc:
        consolidation_seconds = 0.0
        error = f"{type(exc).__name__}: {exc}"
    finally:
        for key, value in previous.items():
            setattr(settings, key, value)

    report = build_variant_report(
        name=name,
        original_tokens=count_tokens(original),
        clean_tokens=count_tokens(prepared),
        chunks=len(chunks),
        preparation_seconds=preparation_seconds,
        chunk_seconds=chunk_seconds,
        consolidation_seconds=consolidation_seconds,
        peak_rss_mb=_peak_rss_mb(),
        chunk_summaries=summaries,
        summary=summary,
        error=error,
    )
    report["critical_path_seconds"] = round(
        preparation_seconds + perf_counter() - wall_started, 3
    )
    report["meets_300_seconds"] = not error and report["critical_path_seconds"] <= 300
    report["configuration"] = variant
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--variants", nargs="+", choices=VARIANTS, default=list(VARIANTS))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-chunks", type=int)
    args = parser.parse_args()
    transcription = extract_transcription(args.input)
    results = [
        run_variant(name, transcription, max_chunks=args.max_chunks)
        for name in args.variants
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
