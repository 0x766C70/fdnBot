"""Garde-fous de l'agent FDN.

Contrôle en amont de chaque question utilisateur :
1. périmètre : seule l'IT et FDN sont autorisés, les autres sujets sont refusés ;
2. usage des outils : la recherche web (limitée à *.fdn.fr) n'est armée que
   quand la question exige des faits propres à FDN.

Le classement tient compte du fil de conversation : une question de suivi
("et le prix ?") hérite du contexte des messages précédents.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field

from fdn_bot.llm import get_small_chat_model

CLASSIFY_CONTEXT_TURNS = 6

REFUSAL = (
    "*Remet une bière au comptoir et sourit* Ici c'est BotBot qui répond, et "
    "ça, malheureusement, ce n'est pas mon rayon : au bistro de FDN, on cause "
    "technique (réseaux, IP, Linux, DNS, fibre, VPN...), association "
    "(offres, adhésion, services, documentation sur fdn.fr) ou cartes des "
    "boissons (cocktails, cafés, thés).\n\n"
    "Repose-moi une question là-dessus, je te sors ça avec le sourire."
)


class TopicClassification(BaseModel):
    """Décision du garde-fou sur le dernier message du fil."""

    in_scope: bool = Field(
        description=(
            "True si la question porte sur l'informatique / l'IT (réseaux, "
            "systèmes, web, programmation, télécoms, cybersécurité...), sur "
            "FDN (l'association, ses offres, ses services), ou sur la "
            "mixologie et les boissons de bar (cocktails, recettes, "
            "dosages, cafés, thés), en tenant compte du contexte du fil : "
            "une question de suivi sur un sujet autorisé abordé avant "
            "reste in_scope. False sinon."
        )
    )
    needs_fdn_facts: bool = Field(
        default=False,
        description=(
            "True uniquement si la réponse exige des faits précis et actuels "
            "propres à FDN (offres, tarifs, procédures d'adhésion, services, "
            "actualités, statut de l'association), y compris pour une "
            "question de suivi dont le fil porte sur FDN. False pour une "
            "question d'IT générale, une salutation ou la conversation courante."
        ),
    )


CLASSIFIER_PROMPT = (
    "Tu es un filtre de modération pour un agent d'assistance. On te donne "
    "le fil de conversation récent (l'utilisateur = User, l'agent = "
    "Assistant) puis la dernière question à classer. Classe cette question "
    "strictement :\n"
    "- in_scope : porte-t-elle sur l'IT (réseaux, IP, Linux, DNS, fibre, "
    "VPN, programmation, cybersécurité, matériel...), sur FDN et son site "
    "fdn.fr (offres, adhésion, services, actualités), ou sur la mixologie "
    "et les boissons de bar (cocktails, recettes, dosages, cafés, thés) ? "
    "Une salutation, une formule de politesse ou un suivi d'un sujet "
    "autorisé du fil reste in_scope. Sois strict : cuisine, sport, météo, "
    "politique hors-numérique, médecine, culture générale -> in_scope=False.\n"
    "- needs_fdn_facts : la réponse exige-t-elle des informations précises "
    "et à jour du site fdn.fr ? Pour un suivi d'un fil qui porte sur FDN, "
    "réponds needs_fdn_facts=True. Pour l'IT générale et la mixologie, "
    "réponds False."
)


def _role_of(message: Any) -> Optional[str]:
    if isinstance(message, HumanMessage) or getattr(message, "type", "") == "human":
        return "User"
    if isinstance(message, AIMessage) or getattr(message, "type", "") == "ai":
        return "Assistant"
    return None


def _transcript(messages: list) -> str:
    lines = []
    for message in messages:
        role = _role_of(message)
        if not role:
            continue
        content = message.content
        text = content if isinstance(content, str) else str(content)
        text = " ".join(text.split())
        if not text:
            continue  # messages intermediaires (tool calls vides)
        lines.append(f"{role} : {text[:300]}")
    return "\n".join(lines)


def classify_thread(messages: list) -> TopicClassification:
    """Classe la dernière question au vu du fil de conversation.

    En cas d'échec, l'exception remonte : l'appelant privilégie alors
    d'armer les outils et de laisser l'agent répondre (fail-open).
    """
    transcript = _transcript(messages[-CLASSIFY_CONTEXT_TURNS:])
    llm = get_small_chat_model()
    structured = llm.with_structured_output(TopicClassification)
    return structured.invoke(
        [
            ("system", CLASSIFIER_PROMPT),
            ("human", f"Fil récent :\n{transcript or '(nouvelle conversation)'}"),
        ]
    )


ClassifyFn = Callable[[list], TopicClassification]


def last_question(messages: list) -> Optional[str]:
    """Texte du dernier message utilisateur de l'historique."""
    for message in reversed(messages):
        if isinstance(message, HumanMessage) or getattr(message, "type", "") == "human":
            content = message.content
            return content if isinstance(content, str) else str(content)
    return None
