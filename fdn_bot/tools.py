"""Outils de l'agent FDN.

Recherche web (Tavily) et lecture de pages, strictement limitées aux sites *.fdn.fr.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx
from langchain_core.tools import tool
from langchain_tavily import TavilySearch

ALLOWED_DOMAINS = ["fdn.fr", "www.fdn.fr"]
MAX_PAGE_CHARS = 20_000


def is_fdn_url(url: str) -> bool:
    """True si l'URL pointe vers fdn.fr ou un sous-domaine de fdn.fr (*.fdn.fr)."""
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return host == "fdn.fr" or host.endswith(".fdn.fr")


def build_search_tool() -> TavilySearch:
    """Recherche web Tavily restreinte au domaine fdn.fr (et ses sous-domaines)."""
    return TavilySearch(
        name="search_on_fdn",
        description=(
            "Recherche sur le web, restreinte aux sites *.fdn.fr (site officiel de "
            "l'association FDN). Une requête en français fonctionne mieux, par "
            "exemple : \"offre fibre\", \"adhésion\", \"VPN\"."
        ),
        max_results=5,
        search_depth="advanced",
        include_domains=ALLOWED_DOMAINS,
    )


class _TextExtractor(HTMLParser):
    """Extraction du texte visible d'une page HTML (stdlib, sans dépendance)."""

    _SKIP = {"script", "style", "noscript", "template", "head"}
    _BLOCK = {
        "p", "div", "section", "article", "li", "ul", "ol", "br",
        "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._BLOCK:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag in self._BLOCK:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and data.strip():
            self._chunks.append(data)

    @property
    def text(self) -> str:
        raw = "".join(self._chunks)
        return re.sub(r"\n{3,}", "\n\n", raw).strip()


@tool
def read_fdn_page(url: str) -> str:
    """Lit une page web et retourne son texte, UNIQUEMENT si elle est hébergée
    sur fdn.fr ou un sous-domaine (*.fdn.fr). Refuse toute autre URL.

    Utilise cet outil après `search_on_fdn` pour lire le contenu complet
    d'une page fdn.fr repérée dans les résultats de recherche.
    """
    if not is_fdn_url(url):
        return (
            f"URL refusée : {url} n'est pas un site *.fdn.fr. "
            "Je ne peux lire que des pages du domaine fdn.fr."
        )
    try:
        response = httpx.get(
            url,
            timeout=15,
            follow_redirects=True,
            headers={"User-Agent": "fdnBot/0.1.0 (+https://www.fdn.fr)"},
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return f"Échec du téléchargement de {url} : {exc}"

    final_url = str(response.url)
    if not is_fdn_url(final_url):
        return f"Redirection hors du domaine fdn.fr refusée ({final_url})."

    extractor = _TextExtractor()
    extractor.feed(response.text)
    text = extractor.text
    if not text:
        return f"La page {url} ne contient pas de texte exploitable."
    if len(text) > MAX_PAGE_CHARS:
        text = text[:MAX_PAGE_CHARS] + "\n\n[... page tronquée ...]"
    return f"Contenu de {final_url} :\n\n{text}"
