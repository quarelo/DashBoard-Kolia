from scripts.benchmark_analysis import build_variant_report, prepare_variant_text


def test_build_variant_report_calculates_reduction_and_critical_path():
    report = build_variant_report(
        name="hybrid",
        original_tokens=40000,
        clean_tokens=30000,
        chunks=12,
        preparation_seconds=1.5,
        chunk_seconds=[10.0, 12.0],
        consolidation_seconds=20.0,
        peak_rss_mb=1024.0,
        summary={"resumo_geral": "ok", "decisoes_tomadas": []},
        error=None,
    )

    assert report["token_reduction_ratio"] == 0.25
    assert report["critical_path_seconds"] == 43.5
    assert report["required_field_coverage"] == 2 / 9
    assert report["meets_300_seconds"] is True


def test_prepare_variant_text_applies_retention_ratio():
    text = (
        "[LOCUTOR 1]: Explicação genérica longa sobre menus do sistema. "
        "[LOCUTOR 2]: Foi decidido enviar R$ 500 amanhã."
    )

    selected = prepare_variant_text(text, {"clean": True, "retention": 0.5})

    assert "R$ 500" in selected
    assert "menus do sistema" not in selected
