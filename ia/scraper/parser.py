"""Parse the TOTVS "Produtos A-Z" catalogue page into clean product records.

The page (WordPress, server-rendered) lists every product as an
`<article class="produtos-az-item ...">`, each already carrying its own name,
link and description directly in the markup — confirmed against the live page:

    <article class="produtos-az-item col-lg-6" data-az-nome="..." ...>
      <h3 class="produtos-az-item-titulo">
        <a href="https://produtos.totvs.com/produto/agro/fitossanitario/">TOTVS Agro Fitossanitário</a>
      </h3>
      <div class="produtos-az-item-desc">O TOTVS Agro Fitossanitário é ...</div>
      <a href="..." class="btn btn-md btn-purple-outline produtos-az-item-btn">Saiba mais</a>
    </article>

so there is no need to crawl each product's own page for name/description/url.
The `data-az-nome`/`data-az-desc` attributes on the article are lowercase
copies used by the page's own JS filter — the visible `<a>`/`<div>` text is
used instead so the stored name and description keep proper capitalisation.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlparse

from bs4 import BeautifulSoup

# Real entries live under one of two paths: full products under /produto/ and
# companion mobile apps under /aplicativo/ (e.g. "App Meu RH") — confirmed by
# checking every one of the 303 live entries; there is no third pattern. A
# stray element that happens to share the "produtos-az-item" class (the class
# is not namespaced) but links elsewhere — e.g. a blog post or nav item — is
# dropped instead of being silently stored as a product.
_PRODUCT_URL_PATTERN = re.compile(r"^/(?:produto|aplicativo)/", re.IGNORECASE)


@dataclass(frozen=True)
class CatalogueProduct:
    name: str
    description: str
    source_url: str


def _clean_text(value: str) -> str:
    """Collapse whitespace/newlines from the rendered text.

    The description on this page has no nested tags or HTML entities to strip
    (verified against the live markup), so this stays deliberately simple
    rather than running an aggressive HTML-stripping pass that could eat real
    words out of a description that does contain markup later.
    """
    return " ".join(unicodedata.normalize("NFC", value).split())


def _is_product_url(url: str) -> bool:
    return bool(_PRODUCT_URL_PATTERN.match(urlparse(url).path))


def parse_catalogue(html: str) -> list[CatalogueProduct]:
    """Extract, validate and de-duplicate every product listed on the page.

    De-duplication is not theoretical: the live catalogue lists "App Meu RH"
    twice, once under /produto/ and once under /aplicativo/, with the exact
    same name and description but two *different* URLs — a dedupe keyed on
    source_url alone would miss it. The key here is the content itself
    (name + description, case-folded), which is what actually repeats.
    """
    soup = BeautifulSoup(html, "lxml")
    seen_content: set[tuple[str, str]] = set()
    products: list[CatalogueProduct] = []

    for article in soup.select("article.produtos-az-item"):
        link = article.select_one(".produtos-az-item-titulo a[href]")
        description_tag = article.select_one(".produtos-az-item-desc")
        if link is None or description_tag is None:
            continue  # Not a real product entry.

        name = _clean_text(link.get_text())
        description = _clean_text(description_tag.get_text())
        source_url = link["href"].strip()

        if not name or not description or not source_url:
            continue
        if not _is_product_url(source_url):
            continue
        content_key = (name.casefold(), description.casefold())
        if content_key in seen_content:
            continue
        seen_content.add(content_key)

        products.append(CatalogueProduct(name=name, description=description, source_url=source_url))

    return products
