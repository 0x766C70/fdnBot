"""Interface en ligne de commande pour tester l'agent FDN en local.

Usage : uv run python -m fdn_bot
"""

from __future__ import annotations

import sys

from langchain_core.messages import HumanMessage

from fdn_bot.agent import build_agent


def main() -> int:
    print("FDN-Expert - agent expert IT / FDN (fdn.fr). Tapez 'quit' pour sortir.")
    agent = build_agent()
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
        result = agent.invoke({"messages": history}, config={"recursion_limit": 25})
        answer = result["messages"][-1].content
        history = result["messages"]
        print(f"\nFDN-Expert > {answer}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
