"""Assemblage et exécution de l'agent FDN (LangChain 1.x, create_agent)."""

from __future__ import annotations

from typing import Any, Callable

from langchain.agents import create_agent

from fdn_bot import guard
from fdn_bot.llm import get_chat_model
from fdn_bot.prompts import SYSTEM_PROMPT
from fdn_bot.tools import build_search_tool, read_fdn_page

RECURSION_LIMIT = 25


def build_agent(include_search: bool = True):
    """Agent FDN compilé.

    include_search=False armé par le garde-fou pour les questions d'IT
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


def respond(
    messages: list,
    classify_fn: Callable[[str], guard.TopicClassification] = guard.classify_topic,
) -> str:
    """Point d'entrée unique : applique les garde-fous puis exécute l'agent.

    - Question hors périmètre IT/FDN -> refusal immédiat, agent non sollicité.
    - Question IT générale -> agent sans outil de recherche.
    - Question nécessitant des faits FDN -> agent avec recherche *.fdn.fr.
    """
    question = guard.last_question(messages)
    if question is None:
        return "Posez-moi une question d'IT ou sur FDN."

    try:
        classification = classify_fn(question)
    except Exception:  # noqa: BLE001 - échec du filtre : on laisse répondre
        classification = guard.TopicClassification(in_scope=True, needs_fdn_facts=True)

    if not classification.in_scope:
        return guard.REFUSAL

    agent = build_agent(include_search=classification.needs_fdn_facts)
    result = agent.invoke(
        {"messages": messages}, config={"recursion_limit": RECURSION_LIMIT}
    )
    return _extract_text(result["messages"][-1])
