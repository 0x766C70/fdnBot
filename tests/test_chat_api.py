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
