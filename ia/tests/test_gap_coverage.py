"""gap_coverage_service.match_gaps: a decisão de faixa e o cache de embedding.

Como em test_product_service.py, a ordenação contra a `ai.products` real precisa
de Postgres e fica fora daqui — o que estes testes fixam é a regra que a
calibração produziu (margem, não distância absoluta) e o contrato de que texto
repetido não vira chamada de modelo repetida. Nenhum teste aqui toca o Ollama:
`_ranked` é substituído, então a suíte roda fora da rede do Compose como o
CLAUDE.md da raiz exige.
"""
from dataclasses import dataclass

import pytest

from src.app.core.config import settings
from src.app.services import gap_coverage_service as svc


@dataclass
class _FakeProduct:
    name: str
    source_url: str


def _ranking(distances: list[float]):
    """Um ranking falso com as distâncias pedidas, já ordenado."""
    return [
        (_FakeProduct(name=f"Produto {i}", source_url=f"https://totvs.com/{i}"), d)
        for i, d in enumerate(distances)
    ]


@pytest.fixture(autouse=True)
def _isolate_from_ollama(monkeypatch):
    """Cache limpo e nenhuma chamada real de embedding.

    `match_gaps` aquece o cache em lote antes de rankear, então sem este stub
    todo teste daqui bateria no Ollama — e a suíte da IA roda fora da rede do
    Compose justamente para que um teste sem mock falhe em vez de passar
    chamando o modelo de verdade (ver o CLAUDE.md da raiz).
    """
    svc._EMBEDDING_CACHE.clear()
    monkeypatch.setattr(
        svc, "generate_embeddings",
        lambda texts: [[0.1] * settings.embedding_dim for _ in texts],
    )
    yield
    svc._EMBEDDING_CACHE.clear()


def test_margem_larga_vira_cobertura_provavel(monkeypatch):
    # d1=0.20, d5=0.30 -> margem 0.10, bem acima de likely_margin (0.055)
    monkeypatch.setattr(svc, "_ranked", lambda db, gap, k: _ranking([0.20, 0.22, 0.25, 0.28, 0.30]))

    out = svc.match_gaps(db=None, gaps=["Integração nativa com o PIX"])

    assert out["itens"][0]["cobertura"] == svc.COVERAGE_LIKELY
    assert out["resumo"][svc.COVERAGE_LIKELY] == 1
    assert [p["nome"] for p in out["itens"][0]["produtos"]] == ["Produto 0", "Produto 1"]


def test_catalogo_equidistante_nao_vira_cobertura(monkeypatch):
    """O caso que a calibração mostrou ser o mais comum (65% da carga): o
    catálogo inteiro está à mesma distância do gap, então o vizinho mais próximo
    não quer dizer nada — mesmo com a distância dentro do teto."""
    monkeypatch.setattr(svc, "_ranked", lambda db, gap, k: _ranking([0.28, 0.284, 0.286, 0.288, 0.29]))

    out = svc.match_gaps(db=None, gaps=["Falta de líder de produção definido na empresa"])

    assert out["itens"][0]["cobertura"] == svc.COVERAGE_NONE
    # Sem faixa, nenhum produto sugerido: a tela não deve exibir um palpite ao
    # lado de um rótulo que diz que não há match.
    assert out["itens"][0]["produtos"] == []


def test_margem_larga_mas_vizinho_longe_e_rejeitada(monkeypatch):
    """O teto de sanidade: margem alta não salva um gap que o catálogo todo
    ignora, só indica que um deles o ignora um pouco menos."""
    ceiling = settings.gap_coverage_distance_ceiling
    monkeypatch.setattr(
        svc, "_ranked",
        lambda db, gap, k: _ranking([ceiling + 0.05, 0.40, 0.42, 0.44, ceiling + 0.25]),
    )

    out = svc.match_gaps(db=None, gaps=["Algo que o catálogo não cobre"])

    assert out["itens"][0]["cobertura"] == svc.COVERAGE_NONE


def _middle_band(monkeypatch):
    """Um ranking cuja margem cai entre os dois limiares — a faixa do meio."""
    margin = (settings.gap_coverage_likely_margin + settings.gap_coverage_possible_margin) / 2
    monkeypatch.setattr(
        svc, "_ranked", lambda db, gap, k: _ranking([0.25, 0.26, 0.27, 0.28, 0.25 + margin]),
    )


def test_faixa_do_meio_esta_desligada_por_padrao(monkeypatch):
    """O padrão de hoje: a faixa do meio acerta cerca de metade, e uma sugestão
    errada ao lado de um produto derruba a confiança no card inteiro. Enquanto a
    busca não for corrigida, o que cairia nela conta como sem cobertura — e sem
    produto sugerido, para a tela não exibir um palpite que ela mesma rejeitou."""
    assert settings.gap_coverage_possible_enabled is False
    _middle_band(monkeypatch)

    out = svc.match_gaps(db=None, gaps=["Gestão de frota"])

    assert out["itens"][0]["cobertura"] == svc.COVERAGE_NONE
    assert out["itens"][0]["produtos"] == []
    assert out["resumo"][svc.COVERAGE_POSSIBLE] == 0


def test_faixa_do_meio_volta_a_classificar_quando_religada(monkeypatch):
    """O interruptor é o único passo para religá-la depois que a busca contra o
    nome do produto estiver no lugar e as margens, recalibradas. O resto da
    regra de faixa continua valendo, e é isto que garante que ela não apodreceu
    enquanto estava desligada."""
    monkeypatch.setattr(settings, "gap_coverage_possible_enabled", True)
    _middle_band(monkeypatch)

    out = svc.match_gaps(db=None, gaps=["Gestão de frota"])

    assert out["itens"][0]["cobertura"] == svc.COVERAGE_POSSIBLE
    assert out["itens"][0]["produtos"], "religada, a faixa do meio sugere para humano julgar"


def test_gap_repetido_e_embeddado_uma_vez(monkeypatch):
    """Dois produtos podem citar o mesmo gap, e a mesma página reabre várias
    vezes: repetir o texto não pode repetir a chamada ao modelo."""
    lotes = []

    def spy(texts):
        lotes.append(list(texts))
        return [[0.1] * settings.embedding_dim for _ in texts]

    monkeypatch.setattr(svc, "generate_embeddings", spy)
    monkeypatch.setattr(svc, "_ranked", lambda db, gap, k: _ranking([0.20, 0.22, 0.25, 0.28, 0.30]))

    svc.match_gaps(db=None, gaps=["mesmo gap", "mesmo gap", "mesmo gap"])
    svc.match_gaps(db=None, gaps=["mesmo gap"])

    assert lotes == [["mesmo gap"]], f"embeddou em {len(lotes)} lote(s): {lotes}"
    assert svc.cache_size() == 1


def test_gaps_novos_vao_num_lote_so(monkeypatch):
    """O ganho do lote: o que pesa numa chamada de embedding é o ida-e-volta,
    não o cálculo — medido, 20 gaps custaram 400 ms em 20 chamadas e 147 ms numa
    só. Se alguém voltar a embeddar dentro do laço, isto quebra."""
    lotes = []

    def spy(texts):
        lotes.append(list(texts))
        return [[0.1] * settings.embedding_dim for _ in texts]

    monkeypatch.setattr(svc, "generate_embeddings", spy)
    monkeypatch.setattr(svc, "_ranked", lambda db, gap, k: _ranking([0.20, 0.22, 0.25, 0.28, 0.30]))

    svc.match_gaps(db=None, gaps=["gap a", "gap b", "gap c", "gap d"])

    assert lotes == [["gap a", "gap b", "gap c", "gap d"]]


def test_lote_pede_so_o_que_falta_no_cache(monkeypatch):
    """Um produto reaberto depois de outro já ter embeddado parte dos gaps só
    paga pelos novos."""
    svc._store("ja em cache", [0.2] * settings.embedding_dim)
    lotes = []

    def spy(texts):
        lotes.append(list(texts))
        return [[0.1] * settings.embedding_dim for _ in texts]

    monkeypatch.setattr(svc, "generate_embeddings", spy)
    monkeypatch.setattr(svc, "_ranked", lambda db, gap, k: _ranking([0.20, 0.22, 0.25, 0.28, 0.30]))

    svc.match_gaps(db=None, gaps=["ja em cache", "novo"])

    assert lotes == [["novo"]]


def test_lista_vazia_nao_chama_o_modelo(monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("não deveria embeddar sem gap")

    monkeypatch.setattr(svc, "generate_embeddings", fail_if_called)
    monkeypatch.setattr(svc, "_ranked", fail_if_called)

    out = svc.match_gaps(db=None, gaps=["", "   "])

    assert out["itens"] == []
    assert out["resumo"][svc.COVERAGE_NONE] == 0


def test_catalogo_curto_demais_para_margem(monkeypatch):
    """Sem o 5º vizinho não há com o que comparar o 1º — catálogo pequeno (ou
    vazio) falha fechado em "sem cobertura", nunca em cobertura inventada."""
    monkeypatch.setattr(svc, "_ranked", lambda db, gap, k: _ranking([0.1, 0.2]))

    out = svc.match_gaps(db=None, gaps=["Qualquer gap"])

    assert out["itens"][0]["cobertura"] == svc.COVERAGE_NONE
    assert out["itens"][0]["distancia"] is None


# --- aquecimento do startup -------------------------------------------------


class _FakeRow:
    """Linha do `_ALL_GAPS_SQL`: só o atributo que o código lê."""

    def __init__(self, gap: str):
        self.gap = gap


class _FakeDb:
    """Sessão que devolve as linhas pedidas, sem Postgres.

    A consulta de verdade é JSONB sobre `ai.meeting_analyses` e precisa de
    banco, então o que estes testes fixam é o que o aquecimento faz com as
    linhas — não o SQL.
    """

    def __init__(self, gaps: list[str]):
        self._gaps = gaps
        self.params: list[dict] = []

    def execute(self, _statement, params=None):
        self.params.append(params or {})
        return self

    def all(self):
        return [_FakeRow(gap) for gap in self._gaps]


def test_warm_all_gaps_deixa_o_cache_quente(monkeypatch):
    """O motivo de existir: medido, a primeira abertura da Página de Produto
    depois de um `docker compose up` custava 2,36 s porque o serviço começa a
    responder antes de o aquecimento do modelo terminar. Com os gaps já em
    cache, a abertura cai para 0,37 s — e vale para qualquer produto, não só
    para o primeiro que alguém visitar."""
    db = _FakeDb(["gap a", "gap b", "gap c"])

    assert svc.warm_all_gaps(db) == 3
    assert svc.cache_size() == 3

    # E o que foi aquecido não é reembeddado na primeira abertura real.
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("o gap aquecido não deveria ser embeddado de novo")

    monkeypatch.setattr(svc, "generate_embeddings", fail_if_called)
    monkeypatch.setattr(svc, "_ranked", lambda db, gap, k: _ranking([0.20, 0.22, 0.25, 0.28, 0.30]))
    svc.match_gaps(db=None, gaps=["gap a", "gap b"])


def test_warm_all_gaps_sem_gap_nenhum_nao_chama_o_modelo(monkeypatch):
    """Base nova, sem análise: o aquecimento tem de ser um no-op barato, não um
    erro no startup."""
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("não deveria embeddar sem gap")

    monkeypatch.setattr(svc, "generate_embeddings", fail_if_called)

    assert svc.warm_all_gaps(_FakeDb([])) == 0
    assert svc.cache_size() == 0


def test_warm_all_gaps_parte_em_lotes(monkeypatch):
    """Com a base crescendo, o aquecimento não pode virar um corpo único de
    milhares de textos: `_WARM_BATCH` limita o tamanho de cada requisição."""
    lotes = []

    def spy(texts):
        lotes.append(len(texts))
        return [[0.1] * settings.embedding_dim for _ in texts]

    monkeypatch.setattr(svc, "generate_embeddings", spy)
    gaps = [f"gap {i}" for i in range(svc._WARM_BATCH * 2 + 5)]

    assert svc.warm_all_gaps(_FakeDb(gaps)) == len(gaps)
    assert lotes == [svc._WARM_BATCH, svc._WARM_BATCH, 5]


def test_warm_all_gaps_nao_pede_mais_que_o_cache_aguenta():
    """`_store` esvazia o cache inteiro quando enche, então um aquecimento maior
    que `_CACHE_MAX` jogaria fora o que ele mesmo acabou de pôr. O limite é um
    parâmetro do SQL, e este teste é o que garante que ele continue lá."""
    db = _FakeDb([])

    svc.warm_all_gaps(db)

    assert db.params == [{"limite": svc._CACHE_MAX}]
