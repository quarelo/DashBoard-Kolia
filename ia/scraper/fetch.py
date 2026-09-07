"""Fetch the raw HTML of the TOTVS product catalogue page.

A plain GET with a normal browser User-Agent is enough: the page itself is
rendered server-side (WordPress), and a request carrying no User-Agent at all
was the only thing observed to get blocked when this was checked manually. No
headless browser is needed.
"""
import httpx

DEFAULT_CATALOGUE_URL = "https://produtos.totvs.com/produtos-a-z/"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}


def fetch_catalogue_html(url: str = DEFAULT_CATALOGUE_URL, *, timeout: float = 30.0) -> str:
    """Download the catalogue page. Raises httpx.HTTPStatusError on a non-2xx response."""
    response = httpx.get(url, headers=_HEADERS, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return response.text
