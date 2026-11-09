"""Outils de l'agent FDN.

Recherche web (Tavily) et lecture de pages, strictement limitées aux sites *.fdn.fr.
"""

from __future__ import annotations

import io
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx
from langchain_core.tools import tool
from langchain_tavily import TavilySearch

ALLOWED_DOMAINS = ["fdn.fr", "www.fdn.fr"]
MAX_PAGE_CHARS = 20_000
SEARCH_TOOL_NAME = "search_on_fdn"
PDF_MAGIC = b"%PDF-"


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
        name=SEARCH_TOOL_NAME,
        description=(
            "Recherche sur le web, restreinte aux sites *.fdn.fr (site officiel de "
            "l'association FDN). Une requête en français fonctionne mieux, par "
            "exemple : \"offre fibre\", \"adhésion\", \"VPN\"."
        ),
        max_results=5,
        search_depth="advanced",
        include_domains=ALLOWED_DOMAINS,
    )


DOC_EXTENSIONS = (".pdf", ".txt", ".md", ".odt", ".doc", ".docx", ".rtf")
MAX_LISTED_LINKS = 60


class _TextExtractor(HTMLParser):
    """Extraction du texte visible d'une page HTML (stdlib, sans dépendance).

    Conserve aussi les liens <a href> : le modèle a besoin des URLs exactes
    pour suivre les documents (PDF, sous-pages) sans en deviner d'autres.
    """

    _SKIP = {"script", "style", "noscript", "template", "head"}
    _BLOCK = {
        "p", "div", "section", "article", "li", "ul", "ol", "br",
        "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table",
    }

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self._chunks: list[str] = []
        self._skip_depth = 0
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        if tag in self._SKIP:
            self._skip_depth += 1
        if tag in self._BLOCK:
            self._chunks.append("\n")
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                absolute = urljoin(self.base_url, href)
                if is_fdn_url(absolute) and absolute not in self.links:
                    self.links.append(absolute)

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
        body = re.sub(r"\n{3,}", "\n\n", raw).strip()
        if self.links:
            # Documents d'abord : les menus de navigation occupent les
            # premières <a> d'une page et noieraient les PDF sinon.
            ordered = sorted(
                self.links,
                key=lambda url: 0 if url.lower().endswith(DOC_EXTENSIONS) else 1,
            )
            listed = "\n".join(f"- {link}" for link in ordered[:MAX_LISTED_LINKS])
            body = f"{body}\n\nLiens de la page (*.fdn.fr uniquement) :\n{listed}"
        return body


def _shell_limit(text: str) -> str:
    if len(text) > MAX_PAGE_CHARS:
        return text[:MAX_PAGE_CHARS] + "\n\n[... contenu tronqué ...]"
    return text


def _is_pdf(content: bytes, content_type: str) -> bool:
    return content[:5] == PDF_MAGIC or content_type.lower() == "application/pdf"


def _pdf_text(data: bytes) -> str:
    """Extrait le texte d'un PDF via pypdf."""
    from pypdf import PdfReader  # import tardif : requis seulement pour les PDF

    reader = PdfReader(io.BytesIO(data))
    pages = [page.extract_text() or "" for page in reader.pages]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(pages)).strip()


@tool
def read_fdn_page(url: str) -> str:
    """Lit une page web (HTML) ou un document PDF et retourne son texte,
    UNIQUEMENT si elle est hébergée sur fdn.fr ou un sous-domaine (*.fdn.fr).
    Refuse toute autre URL.

    Utilise cet outil après `search_on_fdn` pour lire le contenu complet
    d'une page fdn.fr repérée dans les résultats de recherche, y compris
    les PDF (statuts, règlement intérieur, code de conduite...).
    """
    if not is_fdn_url(url):
        return (
            f"URL refusée : {url} n'est pas un site *.fdn.fr. "
            "Je ne peux lire que des pages du domaine fdn.fr."
        )
    try:
        response = httpx.get(
            url,
            timeout=20,
            follow_redirects=True,
            headers={"User-Agent": "fdnBot/0.1.0 (+https://www.fdn.fr)"},
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return f"Échec du téléchargement de {url} : {exc}"

    final_url = str(response.url)
    if not is_fdn_url(final_url):
        return f"Redirection hors du domaine fdn.fr refusée ({final_url})."

    content_type = response.headers.get("Content-Type", "")
    if _is_pdf(response.content, content_type):
        try:
            text = _pdf_text(response.content)
        except Exception as exc:  # noqa: BLE001
            return (
                f"Le document {final_url} est un PDF mais son texte n'a pas pu "
                f"être extrait ({exc}). Ne devine PAS son contenu : dis que "
                "le PDF est illisible et invite à le consulter directement."
            )
        if not text:
            return (
                f"Le PDF {final_url} semble ne contenir aucun texte extrait "
                "(probablement scanné). Ne devine PAS son contenu : dis que le "
                "document n'est pas lisible par l'outil et donne le lien."
            )
        return f"Contenu du PDF {final_url} :\n\n{_shell_limit(text)}"

    extractor = _TextExtractor(final_url)
    extractor.feed(response.text)
    text = extractor.text
    if not text:
        return f"La page {url} ne contient pas de texte exploitable."
    return f"Contenu de {final_url} :\n\n{_shell_limit(text)}"
