from src.app.services.chunk_service import clean_chunk_text, sanitize_transcription


def test_sanitize_transcription_removes_null_bytes_and_extra_whitespace():
    assert sanitize_transcription("texto\x00  com\n espaços") == "texto com espaços"


def test_clean_chunk_text_removes_small_talk_case_insensitively():
    assert clean_chunk_text("Bom dia, tudo bem? Cliente aprovou a proposta.") == (
        ", ? Cliente aprovou a proposta."
    )
