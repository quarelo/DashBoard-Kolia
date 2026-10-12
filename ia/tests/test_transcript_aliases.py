from src.app.services.transcript_aliases import normalize_aliases


def test_normalize_aliases_fixes_transcribed_product_names():
    assert normalize_aliases("o Totus e o Proteus") == "o TOTVS e o Protheus"
    assert normalize_aliases("TOTOS, tots e TOTUS") == "TOTVS, TOTVS e TOTVS"
    assert normalize_aliases("ligar o Transmit") == "ligar o TOTVS Transmite"
    assert normalize_aliases("Totus Transmit") == "TOTVS Transmite"
    assert normalize_aliases("AppFlux ou openflux") == "Upflux ou Upflux"


def test_normalize_aliases_leaves_ordinary_words_alone():
    text = "o processo vai fluir melhor; o sistema transmite o arquivo; totós"
    assert normalize_aliases(text) == text


def test_normalize_aliases_respects_word_boundaries():
    assert normalize_aliases("Proteusx totusa") == "Proteusx totusa"
