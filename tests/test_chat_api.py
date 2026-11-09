"""Tests unitaires de fdn_bot et de la fonction Vercel api/chat.py.

Sans clés API : uniquement la logique pure (garde-fou domaine, conversions).
Avec clés API : lancer `uv run --no-sync python -m fdn_bot` ou les exemples
du README pour vérifier l'enchaînement complet Mistral + Tavily.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "api"))

from fdn_bot.tools import is_fdn_url  # noqa: E402


class TestGardeFouDomaine:
    def test_autorise_fdn_fr(self):
        assert is_fdn_url("https://www.fdn.fr/adherer/")
        assert is_fdn_url("https://fdn.fr/")
        assert is_fdn_url("http://wiki.fdn.fr/tuto")

    def test_refuse_autres_domaines(self):
        assert not is_fdn_url("https://google.com/")
        assert not is_fdn_url("https://example.org/fdn.fr")

    def test_refuse_suffixes_etrangers(self):
        # ressemble à fdn.fr mais n'est pas un sous-domaine
        assert not is_fdn_url("https://evil-fdn.fr/")
        assert not is_fdn_url("https://fdn.fr.evil.com/")
        assert not is_fdn_url("https://xn--fdn-2va.fr/")

    def test_url_invalide(self):
        assert not is_fdn_url("")
        assert not is_fdn_url("pas une url")


class TestConversionApiChat:
    def test_historique_complet(self):
        import chat

        messages = chat._messages_from_payload({
            "messages": [
                {"role": "user", "content": "Bonjour"},
                {"role": "assistant", "content": "Salut"},
                {"role": "user", "content": "Quels sont les tarifs ?"},
            ]
        })
        assert [m.type for m in messages] == ["human", "ai", "human"]

    def test_dernier_message_doit_etre_utilisateur(self):
        import chat

        with pytest.raises(ValueError):
            chat._messages_from_payload(
                {"messages": [{"role": "assistant", "content": "x"}]}
            )
        with pytest.raises(ValueError):
            chat._messages_from_payload({"messages": []})

    def test_extraction_texte(self):
        import chat
        from langchain_core.messages import HumanMessage

        assert chat._extract_text(HumanMessage(content="ok")) == "ok"
        assert chat._extract_text(HumanMessage(content=[{"text": "a"}, {"text": "b"}])) == "ab"


class TestRoutesFastApi:
    """Tests des routes de l'app (sans clé API : pas d'appel à l'agent)."""

    def _request(self, method: str, path: str, **kwargs) -> "httpx.Response":
        import asyncio

        import httpx
        from httpx import ASGITransport
        from chat import app

        async def run() -> httpx.Response:
            async with httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url="http://testserver"
            ) as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(run())

    def test_health(self):
        r = self._request("GET", "/api/chat")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_index_sert_l_interface(self):
        r = self._request("GET", "/")
        assert r.status_code == 200
        assert "FDN-Expert" in r.text

    def test_chat_requete_invalide(self):
        r = self._request("POST", "/api/chat", json={"messages": []})
        assert r.status_code == 400
        r = self._request(
            "POST", "/api/chat", json={"messages": [{"role": "assistant", "content": "x"}]}
        )
        assert r.status_code == 400
