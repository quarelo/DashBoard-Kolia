from src.app.services.speaker_roles import detect_vendor_speakers, format_speaker_context


def test_sellers_are_found_by_their_introduction_in_both_tag_formats():
    transcript = (
        "[LOCUTOR 43]: Bom dia, eu sou o Fulano, sou aqui do comercial da Totos.\n"
        "[LOCUTOR 7]: Bom dia, a gente usa o Totvs faz dez anos.\n"
        "[L1]: Sou especialista aqui da plataforma Tots Assinatura Eletrônica.\n"
        "[L9]: E eu sou executiva de contas aqui da [EMPRESA].\n"
        "[L12]: Nós somos uma empresa investida pela TOTUS.\n"
        "[L43]: Seguindo.\n"
    )

    assert detect_vendor_speakers(transcript) == ["43", "1", "9", "12"]


def test_a_client_that_mentions_totvs_is_not_a_seller():
    transcript = (
        "[L3]: A gente usa o Totvs no financeiro.\n"
        "[L4]: Somos clientes da Totvs há anos.\n"
        "[L5]: Eu sou aqui da área fiscal, usamos Totvs.\n"
        "[L6]: Sou o diretor comercial aqui da [EMPRESA].\n"
    )

    assert detect_vendor_speakers(transcript) == []


def test_speaker_context_names_sellers_and_the_client_rule():
    line = format_speaker_context(["43", "1"])

    assert line.startswith("Locutores da TOTVS (vendedores/especialistas): L43, L1.")
    assert "Os demais são do cliente." in line
    assert "só contam quando ditos pelo cliente" in line
    assert format_speaker_context([]) is None
