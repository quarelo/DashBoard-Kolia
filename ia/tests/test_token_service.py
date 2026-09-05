from src.app.services.token_service import count_tokens, split_text_by_tokens


def test_count_tokens_counts_words_and_punctuation():
    assert count_tokens("Olá, mundo!") == 4


def test_split_text_by_tokens_preserves_overlap():
    chunks = split_text_by_tokens(
        "um dois tres quatro cinco seis",
        max_tokens=4,
        overlap_tokens=2,
    )

    assert chunks == ["um dois tres quatro", "tres quatro cinco seis"]


def test_split_text_prefers_sentence_boundary_inside_chunk_window():
    chunks = split_text_by_tokens(
        "A B C . D E F G H I .", max_tokens=8, overlap_tokens=2
    )

    assert chunks[0].endswith(".")
    assert "D" in chunks[1]


def test_split_text_by_tokens_rejects_invalid_limits():
    try:
        split_text_by_tokens("texto", max_tokens=2, overlap_tokens=2)
    except ValueError as error:
        assert str(error) == "overlap_tokens must be smaller than max_tokens"
    else:
        raise AssertionError("invalid chunk limits must be rejected")


def test_chunks_preserve_the_original_spacing():
    """Chunks are sliced from the text, not rebuilt by joining tokens.

    Joining with " " rewrote "[L67]:" as "[ L67 ] :" and "sexta-feira" as
    "sexta - feira", and that mangled wording reached every quoted evidence
    string in a multi-chunk analysis.
    """
    text = " ".join(
        f"[L{index}]: entrega na sexta-feira, R$ 40 mil (item {index})."
        for index in range(1, 61)
    )
    chunks = split_text_by_tokens(text, 60, 5)

    assert len(chunks) > 1, "o caso só aparece quando o texto é realmente fatiado"
    joined = " ".join(chunks)
    assert "[ L" not in joined
    assert "sexta - feira" not in joined
    assert "sexta-feira" in joined
    assert "R$ 40" in joined


def test_every_chunk_is_a_literal_substring_of_the_input():
    text = " ".join(f"[L{i}]: fato número {i}; detalhe extra." for i in range(1, 41))
    for chunk in split_text_by_tokens(text, 40, 4):
        assert chunk in text
