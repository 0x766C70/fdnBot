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

from fdn_bot import guard
from fdn_bot.agent import respond_with_meta
from fdn_bot.tools import is_fdn_url  # noqa: E402


class TestGardeFou:
    """Contrôle de périmètre et d'outillage, sans appel réseau."""

    def test_refus_hors_perimetre(self):
        from langchain_core.messages import HumanMessage

        def off_topic(messages: list) -> guard.TopicClassification:
            return guard.TopicClassification(in_scope=False)

        meta = respond_with_meta(
            [HumanMessage(content="recette des crepes")], classify_fn=off_topic
        )
        assert meta["answer"] == guard.REFUSAL
        assert meta["refused"] is True
        assert meta["search_used"] is False

    def test_transcript_du_fil(self):
        from langchain_core.messages import AIMessage, HumanMessage

        messages = [
            HumanMessage(content="Quelle est l'offre fibre ?"),
            AIMessage(content="Reponse sur la fibre."),
            HumanMessage(content="et le prix ?"),
        ]
        transcript = guard._transcript(messages)
        assert "offre fibre" in transcript
        assert "et le prix ?" in transcript
        assert "User :" in transcript and "Assistant :" in transcript

    def test_derniere_question_extraite(self):
        from langchain_core.messages import AIMessage, HumanMessage

        messages = [
            HumanMessage(content="premiere question"),
            AIMessage(content="reponse"),
            HumanMessage(content="derniere question"),
        ]
        assert guard.last_question(messages) == "derniere question"
        assert guard.last_question([]) is None

    def test_classification_schema_defauts(self):
        c = guard.TopicClassification(in_scope=True)
        assert c.needs_fdn_facts is False


class TestSearchUsed:
    """L'indicateur search_used reflete les appels d'outils réels."""

    @staticmethod
    def _fake_agent(monkeypatch, tool_calls, existing_state=None):
        from langchain_core.messages import AIMessage

        class FakeAgent:
            def get_state(self, config):
                class State:
                    values = existing_state or {}
                return State()

            def invoke(self, state, config=None):
                last = AIMessage(content="reponse factice")
                if tool_calls:
                    last.tool_calls = [
                        {"name": "search_on_fdn", "args": {}, "id": "1"}
                    ]
                return {"messages": [last]}

        monkeypatch.setattr("fdn_bot.agent.build_agent", lambda **kw: FakeAgent())

    def test_avec_appel_outil(self, monkeypatch):
        from langchain_core.messages import HumanMessage
        import fdn_bot.agent as agent_mod

        def fdn_topic(messages: list) -> guard.TopicClassification:
            return guard.TopicClassification(in_scope=True, needs_fdn_facts=True)

        self._fake_agent(monkeypatch, tool_calls=True)
        meta = agent_mod.respond_with_meta(
            [HumanMessage(content="offre fibre FDN ?")], classify_fn=fdn_topic
        )
        assert meta["search_used"] is True
        assert meta["refused"] is False

    def test_sans_appel_outil(self, monkeypatch):
        from langchain_core.messages import HumanMessage
        import fdn_bot.agent as agent_mod

        def it_topic(messages: list) -> guard.TopicClassification:
            return guard.TopicClassification(in_scope=True, needs_fdn_facts=False)

        self._fake_agent(monkeypatch, tool_calls=False)
        meta = agent_mod.respond_with_meta(
            [HumanMessage(content="c'est quoi un VLAN ?")], classify_fn=it_topic
        )
        assert meta["search_used"] is False


class TestMemoireThread:
    """Memoire serveur : thread_id -> checkpointer InMemorySaver."""

    @staticmethod
    def _capture_agent(monkeypatch, existing_state, captured):
        class FakeAgent:
            def get_state(self, config):
                class State:
                    values = existing_state or {}
                return State()

            def invoke(self, state, config=None):
                captured["payload"] = state
                captured["config"] = config
                from langchain_core.messages import AIMessage
                return {"messages": [AIMessage(content="ok")]}

        monkeypatch.setattr("fdn_bot.agent.build_agent", lambda **kw: FakeAgent())

    def test_nouveau_thread_historique_complet(self, monkeypatch):
        from langchain_core.messages import HumanMessage
        import fdn_bot.agent as agent_mod

        captured = {}
        self._capture_agent(monkeypatch, {}, captured)
        messages = [HumanMessage(content="q1"), HumanMessage(content="q2")]
        agent_mod.respond_with_meta(messages, thread_id="t1", classify_fn=lambda m: guard.TopicClassification(in_scope=True))
        # thread inconnu du checkpointer : l'historique complet re-seme le fil
        assert len(captured["payload"]["messages"]) == 2
        assert captured["config"]["configurable"]["thread_id"] == "t1"

    def test_thread_connaisseur_dernier_message_seulement(self, monkeypatch):
        from langchain_core.messages import AIMessage, HumanMessage
        import fdn_bot.agent as agent_mod

        captured = {}
        self._capture_agent(
            monkeypatch, {"messages": [HumanMessage(content="ancien fil")]}, captured
        )
        seen_by_classifier = []

        def classifier(messages: list) -> guard.TopicClassification:
            seen_by_classifier.extend(m.content for m in messages)
            return guard.TopicClassification(in_scope=True)

        messages = [
            HumanMessage(content="question ancienne"),
            AIMessage(content="reponse ancienne"),
            HumanMessage(content="nouvelle question"),
        ]
        agent_mod.respond_with_meta(messages, thread_id="t2", classify_fn=classifier)
        # thread deja connu : un seul message envoye a l'agent (le dernier)
        assert len(captured["payload"]["messages"]) == 1
        assert captured["payload"]["messages"][0].content == "nouvelle question"
        assert captured["config"]["configurable"]["thread_id"] == "t2"
        # et le garde-fou a vu l'etat du checkpointer + le nouveau message
        assert "ancien fil" in seen_by_classifier
        assert "nouvelle question" in seen_by_classifier

    def test_sans_thread_id_historique_complet(self, monkeypatch):
        from langchain_core.messages import HumanMessage
        import fdn_bot.agent as agent_mod

        captured = {}
        self._capture_agent(monkeypatch, {}, captured)
        messages = [HumanMessage(content="q1"), HumanMessage(content="q2")]
        agent_mod.respond_with_meta(
            messages, classify_fn=lambda m: guard.TopicClassification(in_scope=True)
        )
        assert len(captured["payload"]["messages"]) == 2
        assert "configurable" not in captured["config"]


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
        from fdn_bot.agent import _extract_text
        from langchain_core.messages import HumanMessage

        assert _extract_text(HumanMessage(content="ok")) == "ok"
        assert _extract_text(HumanMessage(content=[{"text": "a"}, {"text": "b"}])) == "ab"


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
