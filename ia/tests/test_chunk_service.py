from src.app.services.chunk_service import (
    clean_chunk_text,
    clean_transcription,
    sanitize_transcription,
    select_relevant_transcription,
    rank_chunk_indices_for_partial,
)


def test_sanitize_transcription_removes_null_bytes_and_extra_whitespace():
    assert sanitize_transcription("texto\x00  com\n espaços") == "texto com espaços"


def test_clean_chunk_text_removes_small_talk_case_insensitively():
    assert clean_chunk_text("Bom dia, tudo bem? Cliente aprovou a proposta.") == (
        "Bom dia, tudo bem? Cliente aprovou a proposta."
    )


def test_clean_transcription_compacts_merges_and_removes_small_talk_turns():
    text = (
        "[LOCUTOR 12]: Boa tarde.\n"
        "[LOCUTOR 7]: A entrega é dia 20.\n"
        "[LOCUTOR 7]: Não pode atrasar.\n"
        "[LOCUTOR 8]: Obrigado."
    )

    assert clean_transcription(text) == (
        "[L7]: A entrega é dia 20. Não pode atrasar."
    )


def test_clean_transcription_preserves_substantive_question_and_numbers():
    text = (
        "[LOCUTOR 2]: Tudo bem?\n"
        "[LOCUTOR 3]: O valor não será R$ 500 até sexta-feira?"
    )

    assert clean_transcription(text) == (
        "[L3]: O valor não será R$ 500 até sexta-feira?"
    )


def test_clean_transcription_removes_exact_duplicate_turns():
    text = (
        "[LOCUTOR 4]: Cliente aprovou a proposta.\n"
        "[LOCUTOR 4]: Cliente aprovou a proposta."
    )

    assert clean_transcription(text) == "[L4]: Cliente aprovou a proposta."


def test_relevance_selection_prioritizes_critical_facts_and_keeps_order():
    text = (
        "[LOCUTOR 1]: A apresentação possui diversos menus e telas explicativas.\n"
        "[LOCUTOR 2]: O contrato não pode passar de R$ 500 até sexta-feira.\n"
        "[LOCUTOR 3]: Vamos navegar agora por outra tela genérica do sistema.\n"
        "[LOCUTOR 4]: Foi decidido enviar a proposta amanhã."
    )

    selected = select_relevant_transcription(text, retention_ratio=0.5)

    assert "R$ 500" in selected
    assert "Foi decidido" in selected
    assert selected.index("R$ 500") < selected.index("Foi decidido")
    assert "menus e telas" not in selected


def test_relevance_selection_validates_ratio():
    try:
        select_relevant_transcription("texto", retention_ratio=0)
    except ValueError as error:
        assert "maior que 0" in str(error)
    else:
        raise AssertionError("retenção zero deve ser rejeitada")


def test_partial_ranking_covers_timeline_and_prioritizes_signals():
    chunks = [
        "Abertura e contexto da reunião.",
        "Explicação genérica do menu.",
        "Foi decidido enviar R$ 500 amanhã.",
        "Descrição rotineira sem decisão.",
        "Existe dúvida: não podemos manter 40 licenças?",
        "Detalhes comuns do processo.",
        "No encerramento, agendar a ação para segunda-feira.",
    ]

    ranked = rank_chunk_indices_for_partial(chunks, limit=5)

    assert {0, 3, 6}.issubset(ranked)
    assert {2, 4}.issubset(ranked)
    assert len(ranked) == len(set(ranked)) == 5
