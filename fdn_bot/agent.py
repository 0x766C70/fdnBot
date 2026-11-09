"""Assemblage et exécution de l'agent FDN (LangChain 1.x, create_agent)."""

from __future__ import annotations

from typing import Any, Callable

from langchain.agents import create_agent

from fdn_bot import guard
from fdn_bot.llm import get_chat_model
from fdn_bot.prompts import SYSTEM_PROMPT
from fdn_bot.tools import SEARCH_TOOL_NAME, build_search_tool, read_fdn_page

RECURSION_LIMIT = 25
SEARCH_TOOL_NAMES = {SEARCH_TOOL_NAME, "read_fdn_page"}


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
        name="fdn_expert",
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


def respond_with_meta(
    messages: list,
    classify_fn: guard.ClassifyFn = guard.classify_thread,
) -> dict:
    """Point d'entrée unique : applique les garde-fous puis exécute l'agent.

    Retourne {"answer": str, "refused": bool, "search_used": bool}."""
    question = guard.last_question(messages)
    if question is None:
        return {"answer": "Posez-moi une question d'IT ou sur FDN.", "refused": True, "search_used": False}

    try:
        classification = classify_fn(messages)
    except Exception:  # noqa: BLE001 - échec du filtre : on laisse répondre
        classification = guard.TopicClassification(in_scope=True, needs_fdn_facts=True)

    if not classification.in_scope:
        return {"answer": guard.REFUSAL, "refused": True, "search_used": False}

    agent = build_agent(include_search=classification.needs_fdn_facts)
    result = agent.invoke(
        {"messages": messages}, config={"recursion_limit": RECURSION_LIMIT}
    )
    return {
        "answer": _extract_text(result["messages"][-1]),
        "refused": False,
        "search_used": _search_used(result["messages"]),
    }


def respond(messages: list, classify_fn: guard.ClassifyFn = guard.classify_thread) -> str:
    """Version simple de respond_with_meta, pour la CLI et l'API legacy."""
    return respond_with_meta(messages, classify_fn)["answer"]
