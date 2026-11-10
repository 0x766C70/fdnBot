"""Assemblage et exécution de l'agent FDN (LangChain 1.x, create_agent).

Mémoire de conversation : checkpointer LangGraph InMemorySaver, indexé par
thread_id (l'état du fil persiste entre les appels de l'instance serveur).
Sur serverless, une instance frode repart à vide : l'appelant transmet
alors l'historique complet, qui re-seme le thread au besoin.
"""

from __future__ import annotations

import uuid
from typing import Any, Callable, Optional

from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver

from fdn_bot import guard
from fdn_bot.llm import get_chat_model
from fdn_bot.prompts import SYSTEM_PROMPT
from fdn_bot.tools import SEARCH_TOOL_NAME, build_search_tool, read_fdn_page

RECURSION_LIMIT = 25
SEARCH_TOOL_NAMES = {SEARCH_TOOL_NAME, "read_fdn_page"}

# Checkpointer partagé par tous les agents du process : c'est lui qui porte
# la mémoire des fils entre les requêtes.
CHECKPOINTER = InMemorySaver()


def build_agent(include_search: bool = True):
    """Agent FDN compilé.

    include_search=False (décidé par le garde-fou) pour les questions d'IT
    générale : l'agent répond alors sans outil de recherche web.
    """
    tools = [build_search_tool(), read_fdn_page] if include_search else []
    return create_agent(
        get_chat_model(),
        tools,
        system_prompt=SYSTEM_PROMPT,
        checkpointer=CHECKPOINTER,
        name="botbot",
    )


def _extract_text(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "") for block in content if isinstance(block, dict)
        )
    return str(content)


def _search_used(result_messages: list) -> bool:
    """True si l'agent a réellement appelé un outil de recherche fdn.fr."""
    for message in result_messages:
        tool_calls = getattr(message, "tool_calls", None)
        if not tool_calls:
            continue
        for call in tool_calls:
            name = call.get("name", "") if isinstance(call, dict) else getattr(call, "name", "")
            if name in SEARCH_TOOL_NAMES:
                return True
    return False


def _thread_state_messages(agent: Any, thread_id: str) -> list:
    """Messages connus du checkpointer pour ce thread (vide si thread neuf)."""
    try:
        state = agent.get_state({"configurable": {"thread_id": thread_id}})
    except Exception:  # noqa: BLE001
        return []
    values = getattr(state, "values", None) or {}
    return list(values.get("messages", []))


def respond_with_meta(
    messages: list,
    thread_id: Optional[str] = None,
    classify_fn: guard.ClassifyFn = guard.classify_thread,
) -> dict:
    """Point d'entrée unique : applique les garde-fous puis exécute l'agent.

    Retourne {"answer": str, "refused": bool, "search_used": bool}.

    thread_id : active la memoire serveur (InMemorySaver). Si le thread
    est deja connu du checkpointer, seul le dernier message est envoye a
    l'agent (l'historique vit dans l'etat du graph) et le garde-fou
    classifie au vu de l'etat du fil. Sinon, l'historique complet fourni
    re-seme le thread (cas des instances froides du serverless).
    """
    question = guard.last_question(messages)
    if question is None:
        return {"answer": "Posez-moi une question d'IT ou sur FDN.", "refused": True, "search_used": False}

    # Le checkpointer exige un thread_id : sans fil fourni, thread éphémère
    # (comportement stateless équivalent à l'absence de mémoire serveur).
    if not thread_id:
        thread_id = f"ephemeral-{uuid.uuid4()}"

    # Le garde-fou doit voir la memoire serveur du fil, pas seulement le
    # nouveau message : on lui presente l'etat du checkpointer + le message.
    prior_messages: list = []
    if thread_id:
        prior_messages = _thread_state_messages(build_agent(), thread_id)
    classify_messages = prior_messages + messages

    try:
        classification = classify_fn(classify_messages)
    except Exception:  # noqa: BLE001 - échec du filtre : on laisse répondre
        classification = guard.TopicClassification(in_scope=True, needs_fdn_facts=True)

    if not classification.in_scope:
        return {"answer": guard.REFUSAL, "refused": True, "search_used": False}

    agent = build_agent(include_search=classification.needs_fdn_facts)
    config = {
        "recursion_limit": RECURSION_LIMIT,
        "configurable": {"thread_id": thread_id},
        # Observabilite LangSmith : filtration possible par thread et par
        # armement de la recherche dans l'interface smith.langchain.com
        "metadata": {
            "thread_id": thread_id,
            "search_armed": classification.needs_fdn_facts,
        },
        "tags": ["fdnbot", "botbot"],
    }
    # Instance qui connait deja le fil -> seul le nouveau message suffit.
    payload = {"messages": messages[-1:]} if prior_messages else {"messages": messages}
    result = agent.invoke(payload, config)

    return {
        "answer": _extract_text(result["messages"][-1]),
        "refused": False,
        "search_used": _search_used(result["messages"]),
    }


def respond(
    messages: list,
    thread_id: Optional[str] = None,
    classify_fn: guard.ClassifyFn = guard.classify_thread,
) -> str:
    """Version simple de respond_with_meta, pour la CLI et l'API legacy."""
    return respond_with_meta(messages, thread_id, classify_fn)["answer"]
