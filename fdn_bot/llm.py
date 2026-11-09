"""Construction des modèles de chat (Mistral) partagés par l'agent."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_mistralai import ChatMistralAI

load_dotenv()

DEFAULT_MODEL = "mistral-large-latest"
CLASSIFIER_MODEL = "mistral-small-latest"


def get_chat_model() -> ChatMistralAI:
    """Modèle principal de l'agent."""
    return ChatMistralAI(
        model=os.getenv("MISTRAL_MODEL", DEFAULT_MODEL),
        temperature=0.1,
    )


def get_small_chat_model() -> ChatMistralAI:
    """Modèle léger pour les contrôles (classification du garde-fou)."""
    return ChatMistralAI(
        model=os.getenv("MISTRAL_CLASSIFIER_MODEL", CLASSIFIER_MODEL),
        temperature=0.0,
    )
