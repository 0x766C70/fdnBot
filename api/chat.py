"""Fonction serverless Vercel : endpoint chat de l'agent FDN.

GET  /api/chat  -> health check
POST /api/chat  -> {"messages": [{"role": "user"|"assistant", "content": "..."}]}
                   renvoie {"answer": "..."}
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fdn_bot.agent import build_agent  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402

MAX_HISTORY = 20


def _messages_from_payload(payload: dict) -> list:
    """Convertit l'historique JSON client en messages LangChain."""
    messages = []
    for item in payload.get("messages", []):
        role = item.get("role", "user")
        content = (item.get("content") or "").strip()
        if not content:
            continue
        if role == "assistant":
            messages.append(AIMessage(content=content))
        else:
            messages.append(HumanMessage(content=content))
    # Le dernier message doit être une question utilisateur.
    if not messages or not isinstance(messages[-1], HumanMessage):
        raise ValueError("Le dernier message doit être un message utilisateur non vide.")
    return messages[-MAX_HISTORY:]


def _extract_text(message) -> str:  # noqa: ANN001
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "") for block in content if isinstance(block, dict)
        )
    return str(content)


class handler(BaseHTTPRequestHandler):

    def _send_json(self, status: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        self._send_json(200, {"status": "ok", "service": "fdnBot", "agent": "fdn_expert"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
            messages = _messages_from_payload(payload)
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_json(400, {"error": f"Requête invalide : {exc}"})
            return

        try:
            agent = build_agent()
            result = agent.invoke(
                {"messages": messages}, config={"recursion_limit": 25}
            )
            answer = _extract_text(result["messages"][-1])
            self._send_json(200, {"answer": answer})
        except Exception as exc:  # noqa: BLE001
            self._send_json(500, {"error": f"Erreur de l'agent : {exc}"})

    def log_message(self, format: str, *args) -> None:  # noqa: A002, N802
        pass
