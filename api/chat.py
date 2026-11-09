"""Application FastAPI de l'agent FDN, déployable sur Vercel (runtime Python).

L'app est l'unique entrypoint du projet, déclaré dans pyproject.toml via :
    [tool.vercel]
    entrypoint = "api.chat:app"

Routes :
    GET  /           -> interface de chat (public/index.html)
    GET  /api/chat   -> health check
    POST /api/chat   -> {"messages": [{"role": "user"|"assistant", "content": "..."}]}
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from fdn_bot.agent import respond  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402

MAX_HISTORY = 20
INDEX_HTML = _ROOT / "public" / "index.html"


class ChatMessage(BaseModel):
    role: str = "user"
    content: str = ""


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str


app = FastAPI(title="fdnBot", description="Agent expert IT / FDN (fdn.fr)")


@app.exception_handler(HTTPException)
async def _http_exception_handler(request: Any, exc: HTTPException) -> JSONResponse:
    """Erreurs au format {"error": ...} compris par le frontend."""
    return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})


def _messages_from_payload(payload: dict[str, Any]) -> list[Any]:
    """Convertit l'historique JSON client en messages LangChain."""
    messages = []
    for item in payload.get("messages", []):
        content = (item.get("content") or "").strip()
        if not content:
            continue
        if item.get("role") == "assistant":
            messages.append(AIMessage(content=content))
        else:
            messages.append(HumanMessage(content=content))
    # Le dernier message doit être une question utilisateur.
    if not messages or not isinstance(messages[-1], HumanMessage):
        raise ValueError("Le dernier message doit être un message utilisateur non vide.")
    return messages[-MAX_HISTORY:]


@app.get("/")
def index() -> FileResponse:
    if not INDEX_HTML.exists():
        raise HTTPException(status_code=404, detail="Interface introuvable.")
    return FileResponse(INDEX_HTML)


@app.get("/api/chat")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "fdnBot", "agent": "fdn_expert"}


@app.post("/api/chat")
def chat(request: ChatRequest) -> ChatResponse:
    payload = {"messages": [m.model_dump() for m in request.messages]}
    try:
        messages = _messages_from_payload(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        return ChatResponse(answer=respond(messages))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Erreur de l'agent : {exc}") from exc
