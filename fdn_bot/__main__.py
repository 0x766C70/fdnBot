"""Interface en ligne de commande pour tester l'agent FDN en local.

Usage : uv run python -m fdn_bot
"""

from __future__ import annotations

import sys
import uuid

from langchain_core.messages import AIMessage, HumanMessage

from fdn_bot.agent import respond


def main() -> int:
    print("BotBot - agent expert IT / FDN (fdn.fr). Tapez 'quit' pour sortir.")
    thread_id = f"cli-{uuid.uuid4()}"
    history: list = []
    while True:
        try:
            question = input("\nVous > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question or question.lower() in {"quit", "exit", "q"}:
            break
        history.append(HumanMessage(content=question))
        # Memoire serveur par thread ; l'historique re-seme au cas ou l'instance
        # serveur aurait redemarre (CLI locale : le process vit, le fil vit).
        answer = respond(history, thread_id=thread_id)
        history.append(AIMessage(content=answer))
        print(f"\nBotBot > {answer}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
