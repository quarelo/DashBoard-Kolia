"""Parser tests use a small fixture shaped like the real page, not the live
site: the markup below mirrors what was actually observed on
https://produtos.totvs.com/produtos-a-z/ (article.produtos-az-item with a
titled link plus a description div), including the one duplicate the live
catalogue is known to carry.
"""
from scraper.parser import parse_catalogue

_SAMPLE_HTML = """
<html><body>
<nav><a href="https://produtos.totvs.com/institucional/">Institucional</a></nav>
<div id="produtos-az">

  <article class="produtos-az-item col-lg-6" data-az-nome="agro bioenergia">
    <h3 class="produtos-az-item-titulo">
      <a href="https://produtos.totvs.com/produto/agro/totvs-agro-bioenergia/">TOTVS Agro Bioenergia</a>
    </h3>
    <div class="produtos-az-item-desc">
      O TOTVS Agro Bioenergia    é uma solução de gestão
      agroindustrial completa.
    </div>
    <a href="https://produtos.totvs.com/produto/agro/totvs-agro-bioenergia/"
       class="btn btn-md btn-purple-outline produtos-az-item-btn">Saiba mais</a>
  </article>

  <!-- Mirrors a real case: same product cross-listed under /produto/ and
       /aplicativo/ with identical name+description but different URLs. -->
  <article class="produtos-az-item col-lg-6" data-az-nome="app meu rh">
    <h3 class="produtos-az-item-titulo">
      <a href="https://produtos.totvs.com/produto/totvs-rh/app-meu-rh/">App Meu RH</a>
    </h3>
    <div class="produtos-az-item-desc">Aplicativo para o colaborador.</div>
  </article>

  <article class="produtos-az-item col-lg-6" data-az-nome="app meu rh">
    <h3 class="produtos-az-item-titulo">
      <a href="https://produtos.totvs.com/aplicativo/app-meu-rh/">App Meu RH</a>
    </h3>
    <div class="produtos-az-item-desc">Aplicativo para o colaborador.</div>
  </article>

  <article class="produtos-az-item col-lg-6">
    <h3 class="produtos-az-item-titulo">
      <a href="https://produtos.totvs.com/blog/algum-post/">Um post do blog</a>
    </h3>
    <div class="produtos-az-item-desc">Isso não é um produto.</div>
  </article>

  <article class="produtos-az-item col-lg-6">
    <h3 class="produtos-az-item-titulo"><a href="https://produtos.totvs.com/produto/incompleto/"></a></h3>
    <div class="produtos-az-item-desc"></div>
  </article>

</div>
</body></html>
"""


def test_parses_real_products_with_name_description_and_url():
    products = parse_catalogue(_SAMPLE_HTML)
    found = next(p for p in products if p.name == "TOTVS Agro Bioenergia")
    assert found.source_url == "https://produtos.totvs.com/produto/agro/totvs-agro-bioenergia/"
    assert "gestão" in found.description and "agroindustrial completa" in found.description


def test_collapses_internal_whitespace_in_description():
    products = parse_catalogue(_SAMPLE_HTML)
    found = next(p for p in products if p.name == "TOTVS Agro Bioenergia")
    assert "  " not in found.description
    assert "\n" not in found.description


def test_deduplicates_same_product_listed_under_two_different_urls():
    """Same name + description under /produto/ and /aplicativo/ is one product,
    not two — the real catalogue lists "App Meu RH" exactly this way."""
    products = parse_catalogue(_SAMPLE_HTML)
    names = [p.name for p in products]
    assert names.count("App Meu RH") == 1


def test_accepts_both_produto_and_aplicativo_urls():
    products = parse_catalogue(_SAMPLE_HTML)
    found = next(p for p in products if p.name == "App Meu RH")
    assert "/produto/" in found.source_url or "/aplicativo/" in found.source_url


def test_drops_links_outside_the_product_url_pattern():
    products = parse_catalogue(_SAMPLE_HTML)
    assert all(
        "/produto/" in p.source_url or "/aplicativo/" in p.source_url
        for p in products
    )
    assert not any("blog" in p.source_url for p in products)


def test_drops_entries_missing_name_or_description():
    products = parse_catalogue(_SAMPLE_HTML)
    assert not any(p.source_url.endswith("/produto/incompleto/") for p in products)


def test_only_real_products_survive():
    products = parse_catalogue(_SAMPLE_HTML)
    names = sorted(p.name for p in products)
    assert names == ["App Meu RH", "TOTVS Agro Bioenergia"]
