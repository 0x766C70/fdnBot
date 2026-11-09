"""Garde-fous de l'agent FDN.

Contrôle en amont de chaque question utilisateur :
1. périmètre : seule l'IT et FDN sont autorisés, les autres sujets sont refusés ;
2. usage des outils : la recherche web (limitée à *.fdn.fr) n'est armée que
   quand la question exige des faits propres à FDN.
"""

from __future__ import annotations

import os
from typing import Optional

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from fdn_bot.llm import get_chat_model, get_small_chat_model

REFUSAL = (
    "Je suis FDN-Expert, un agent spécialisé en informatique et sur "
    "l'association FDN (fdn.fr). Votre question sort de mon périmètre, "
    "je ne peux pas y répondre.\n\n"
    "Vous pouvez me demander :\n"
    "- des sujets d'IT générale : réseaux, IP, Linux, DNS, fibre, VPN...\n"
    "- tout ce qui concerne FDN : offres, adhésion, services, documentation."
)


class TopicClassification(BaseModel):
    """Décision du garde-fou sur la dernière question posée."""

    in_scope: bool = Field(
        description=(
            "True si la question porte sur l'informatique / l'IT (réseaux, "
            "systèmes, web, programmation, télécoms, cybersécurité...) ou sur "
            "FDN (l'association, ses offres, ses services). False sinon."
        )
    )
    needs_fdn_facts: bool = Field(
        default=False,
        description=(
            "True uniquement si la réponse exige des faits précis et actuels "
            "propres à FDN (offres, tarifs, procédures d'adhésion, services, "
            "actualités, status de l'association). False pour une question "
            "d'IT générale, une salutation ou une conversation courante."
        ),
    )


CLASSIFIER_PROMPT = (
    "Tu es un filtre de modération pour un agent d'assistance. Analyse la "
    "dernière question de l'utilisateur et classe-la strictement :\n"
    "- in_scope : la question porte-t-elle sur l'IT (réseaux, IP, Linux, "
    "DNS, fibre, VPN, programmation, cybersécurité, matériel...) ou sur FDN "
    "et son site fdn.fr (offres, adhésion, services, actualités) ? Une "
    "salutation, une formule de politesse ou une question de suivi sur un "
    "sujet IT/FDN demandé avant reste in_scope.\n"
    "- needs_fdn_facts : la réponse exige-t-elle des informations précises "
    "et à jour du site fdn.fr ? Réponds False pour l'IT générale.\n"
    "Soyez strict : cuisine, sport, météo, politique hors-numérique, "
    "médecine, culture générale -> in_scope=False."
)


def classify_topic(question: str) -> TopicClassification:
    """Classe la question via un modèle léger à sortie structurée.

    En cas d'échec, échoue côté appelant : on préfère armer les outils
    et laisser l'agent répondre plutôt que bloquer l'utilisateur.
    """
    llm = get_small_chat_model()
    structured = llm.with_structured_output(TopicClassification)
    result = structured.invoke(
        [
            ("system", CLASSIFIER_PROMPT),
            ("human", f"Question à classer : {question}"),
        ]
    )
    return result


def last_question(messages: list) -> Optional[str]:
    """Texte du dernier message utilisateur de l'historique."""
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            content = message.content
            return content if isinstance(content, str) else str(content)
        if getattr(message, "type", "") == "human":
            return str(message.content)
    return None
