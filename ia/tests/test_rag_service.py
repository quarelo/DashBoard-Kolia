from src.app.services.rag_service import excerpt_relevance_score, extract_relevant_excerpt


def test_relevant_excerpt_prefers_late_quantified_answer_over_generic_start():
    content = (
        "O CRM possui dashboards, cadastro e diversas configurações gerais. "
        + "demonstração genérica sem a resposta. " * 180
        + "Ao estimar as licenças, ficou combinado fazer o CRM para 25 pessoas. "
        + "O número poderá ser ajustado posteriormente."
    )

    excerpt = extract_relevant_excerpt(
        content,
        "Para quantas pessoas ficou a estimativa de CRM?",
        1200,
    )

    assert "CRM para 25 pessoas" in excerpt
    assert len(excerpt) <= 1200


def test_relevant_excerpt_keeps_natural_start_when_it_contains_the_answer():
    content = (
        "A empresa precisa substituir 27 máquinas porque elas não aceitam Windows 11. "
        + "continuação sem relação. " * 100
    )

    excerpt = extract_relevant_excerpt(
        content,
        "Quantas máquinas precisam ser substituídas e por quê?",
        1200,
    )

    assert excerpt.startswith("A empresa precisa substituir 27 máquinas")


def test_relevant_excerpt_prefers_number_near_requested_unit():
    content = (
        "No CRM, a estimativa para pessoas do comercial será revista. "
        + "detalhes de demonstração sem resposta. " * 35
        + "Serão recuperadas oportunidades perdidas no ano de 25. "
        + "mais detalhes genéricos. " * 35
        + "A estimativa comercial ficou definida como CRM para 25 pessoas. "
        + "O total poderá ser ajustado."
    )

    excerpt = extract_relevant_excerpt(
        content,
        "Para quantas pessoas ficou a estimativa de CRM?",
        1200,
    )

    assert "CRM para 25 pessoas" in excerpt


def test_speaker_label_is_not_scored_as_quantity_of_people():
    query = "Para quantas pessoas ficou a estimativa de CRM?"

    speaker_label_score = excerpt_relevance_score(
        "No CRM, a estimativa foi comentada. [ L61 ] : tipo de pessoa jurídica.",
        query,
    )
    actual_quantity_score = excerpt_relevance_score(
        "No CRM, a estimativa final foi de 25 pessoas.",
        query,
    )

    assert actual_quantity_score > speaker_label_score


def test_relevant_excerpt_prefers_months_for_temporal_question():
    content = (
        "Foi comentado um estudo de cloud, infraestrutura e custos. "
        + "detalhes técnicos sem prazo. " * 90
        + "O estudo será revisto mais adiante, em março ou abril."
    )

    excerpt = extract_relevant_excerpt(
        content,
        "Em que meses ficou combinado revisar o estudo de cloud?",
        1200,
    )

    assert "março ou abril" in excerpt
