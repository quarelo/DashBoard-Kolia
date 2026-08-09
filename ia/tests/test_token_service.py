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


def test_split_text_by_tokens_rejects_invalid_limits():
    try:
        split_text_by_tokens("texto", max_tokens=2, overlap_tokens=2)
    except ValueError as error:
        assert str(error) == "overlap_tokens must be smaller than max_tokens"
    else:
        raise AssertionError("invalid chunk limits must be rejected")
