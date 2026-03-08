"""
modules/chatbot/main.py
─────────────────────────
FastAPI application for the Developer Chatbot.
Exposes streaming SSE endpoints for natural language interactions.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as aioredis
import structlog
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from modules.chatbot.service import ChatbotService
from shared.config import get_settings
from shared.schemas import ChatRole

logger = structlog.get_logger(__name__)
settings = get_settings()

_redis: aioredis.Redis | None = None
_chatbot: ChatbotService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    global _redis, _chatbot
    try:
        _redis = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        await _redis.ping()
        logger.info("chatbot_redis_connected")
    except Exception as exc:
        logger.warning("chatbot_redis_unavailable", error=str(exc))
        _redis = None
    if _redis is not None:
        _chatbot = ChatbotService(_redis)
    logger.info("chatbot_ready", redis_available=(_redis is not None))
    yield
    if _redis:
        await _redis.aclose()


app = FastAPI(
    title="NeuralOps Chatbot",
    version="1.0.0",
    description="AI-powered SRE assistant with real-time system context",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "module": "chatbot"}


@app.post("/chat/{session_id}")
async def chat(session_id: str, request: Request) -> StreamingResponse:
    if _chatbot is None:
        raise HTTPException(503, "Chatbot not ready")
    
    body = await request.json()
    message = body.get("message")
    user_id = body.get("user_id", "anonymous")
    
    if not message:
        raise HTTPException(400, "Message is required")
    
    session = _chatbot.get_or_create_session(session_id, user_id)
    
    async def event_generator():
        async for token in _chatbot.chat(session, message):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield "data: [DONE]\n\n"

    import json
    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/chat/{session_id}/history")
async def get_history(session_id: str) -> list[dict[str, str]]:
    if _chatbot is None:
        raise HTTPException(503)
    return await _chatbot.get_chat_history(session_id)


if __name__ == "__main__":
    uvicorn.run(
        "modules.chatbot.main:app",
        host=settings.api_host,
        port=8070,
        log_level=settings.api_log_level,
        reload=False,
    )
