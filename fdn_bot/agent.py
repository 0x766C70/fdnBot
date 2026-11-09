"""Construction de l'agent FDN avec LangChain 1.x (create_agent)."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_mistralai import ChatMistralAI

from fdn_bot.prompts import SYSTEM_PROMPT
from fdn_bot.tools import build_search_tool, read_fdn_page

DEFAULT_MODEL = "mistral-large-latest"


def build_agent():
    """Retourne l'agent FDN compilé, prêt pour ainvoke/ainvoke streaming."""
    load_dotenv()
    model = ChatMistralAI(
        model=os.getenv("MISTRAL_MODEL", DEFAULT_MODEL),
        temperature=0.1,
    )
    tools = [build_search_tool(), read_fdn_page]
    return create_agent(
        model,
        tools,
        system_prompt=SYSTEM_PROMPT,
        name="fdn_expert",
    )
