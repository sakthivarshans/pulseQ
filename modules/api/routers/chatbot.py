"""
modules/api/routers/chatbot.py
──────────────────────────────
WebSocket chatbot endpoint with:
  - Ping/pong keepalive (every 25 seconds)
  - OpenRouter streaming → Phi-3 automatic fallback via llm_service
  - REST POST fallback endpoint for clients that cannot maintain WebSocket
  - Real context building from PostgreSQL, Redis, MongoDB, ChromaDB
  - classify_intent() keyword-based message intent routing
  - Redis conversation history (last 6 turns, TTL 3600s)
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

router = APIRouter()

# ── System prompt ──────────────────────────────────────────────────────────────
CHATBOT_SYSTEM_PROMPT = """You are PulseQ AI, an expert DevOps engineer and SRE with 15 years of experience. You are embedded inside the PulseQ platform and have access to real infrastructure data provided in your context below.

STRICT RULES YOU MUST FOLLOW:
1. ALWAYS reference specific data from the context. Quote actual metric values, actual file names, actual line numbers, actual error messages. Never give a generic answer when specific data exists in the context.
2. NEVER repeat yourself. Each sentence must add new information.
3. NEVER say things like "I recommend monitoring your metrics" or "you should check your logs" — these are useless. Instead say "your payment-service p99 latency is currently 847ms which is 3x above your baseline of 280ms, this started at 14:32 UTC coinciding with the deployment of commit a4f3b2c".
4. If the context contains active errors or incidents, lead with those immediately.
5. If asked about code, reference the actual file path and line number from the context.
6. If asked to predict issues, reference specific metric trends from the context data.
7. Format code fixes as markdown code blocks with the language specified.
8. Keep answers focused and actionable. Maximum 400 words unless the user asks for detail.
9. If the context does not contain information needed to answer, say exactly what data is missing and how to get it — do not make things up.
10. End every troubleshooting answer with a numbered action list of exactly what to do next."""

# ── Intent keyword mapping ─────────────────────────────────────────────────────
INTENT_KEYWORDS: dict[str, list[str]] = {
    "error_explanation":  ["error", "exception", "failed", "crash", "500", "404", "traceback", "stack"],
    "code_question":      ["code", "function", "file", "line", "class", "module", "import", "bug", "issue"],
    "metric_question":    ["cpu", "memory", "latency", "requests", "traffic", "throughput", "p99", "p95"],
    "incident_question":  ["incident", "outage", "down", "issue", "problem", "alert", "degraded"],
    "prediction_question": ["predict", "will", "going", "risk", "before", "forecast", "trend"],
    "deployment_question": ["deploy", "release", "commit", "push", "rollback", "revert", "merge"],
}


def classify_intent(message: str) -> str:
    lower = message.lower()
    for intent, keywords in INTENT_KEYWORDS.items():
        if any(k in lower for k in keywords):
            return intent
    return "general"


# ── Context data helpers ───────────────────────────────────────────────────────
async def get_active_incidents_summary(pg_session: Any = None) -> list[dict]:
    """Fetch open incidents from PostgreSQL. Returns empty list gracefully."""
    if pg_session is None:
        return []
    try:
        from sqlalchemy import text
        result = await pg_session.execute(
            text(
                "SELECT incident_id, title, severity, status, primary_service, "
                "detected_at, root_cause_summary "
                "FROM incidents WHERE status NOT IN ('resolved','false_positive') "
                "ORDER BY detected_at DESC LIMIT 10"
            )
        )
        rows = result.mappings().all()
        return [dict(r) for r in rows]
    except Exception as exc:
        logger.warning("get_active_incidents_failed", error=str(exc))
        return []


async def get_latest_metrics_from_redis(redis_client: Any = None) -> list[dict]:
    """Fetch latest system metrics from Redis ring buffer."""
    if redis_client is None:
        return []
    try:
        raw = await redis_client.lrange("metrics:system:latest", 0, 5)
        if raw:
            return [json.loads(r) for r in raw if r]
        # Fall back to single-key format
        single = await redis_client.get("metrics:latest")
        if single:
            parsed = json.loads(single)
            return [parsed] if isinstance(parsed, dict) else parsed
        return []
    except Exception as exc:
        logger.warning("get_metrics_from_redis_failed", error=str(exc))
        return []


async def get_repo_errors_summary(mongo_db: Any, project_id: str) -> list[dict]:
    """Fetch top unresolved errors for a project from MongoDB."""
    if mongo_db is None:
        return []
    try:
        cursor = (
            mongo_db["repo_errors"]
            .find(
                {"repo_id": project_id, "is_resolved": {"$ne": True}},
                {
                    "file_path": 1, "line_number": 1, "error_type": 1,
                    "severity": 1, "title": 1, "description": 1, "suggestion": 1,
                },
            )
            .sort([("severity", 1), ("confidence_score", -1)])
            .limit(10)
        )
        errors = []
        async for doc in cursor:
            errors.append({
                "error_id": str(doc.get("_id", "")),
                "file_path": doc.get("file_path", ""),
                "line_number": doc.get("line_number", ""),
                "title": doc.get("title", ""),
                "severity": doc.get("severity", "P3"),
                "error_type": doc.get("error_type", ""),
                "description": doc.get("description", ""),
                "suggestion": doc.get("suggestion", ""),
            })
        return errors
    except Exception as exc:
        logger.warning("get_repo_errors_summary_failed", error=str(exc))
        return []


async def query_similar_incidents(message: str, chroma_client: Any = None) -> list[dict]:
    """Query ChromaDB for past incidents similar to the user's message."""
    if chroma_client is None:
        return []
    try:
        collection = chroma_client.get_collection("historical_incidents")
        results = collection.query(
            query_texts=[message[:500]],
            n_results=3,
            include=["documents", "metadatas"],
        )
        similar = []
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        for doc, meta in zip(docs, metas):
            similar.append({
                "description": doc[:300],
                "metadata": meta,
            })
        return similar
    except Exception as exc:
        logger.warning("query_similar_incidents_failed", error=str(exc))
        return []

async def _empty_list() -> list:
    """Async helper returning empty list — replaces removed asyncio.coroutine in Python 3.11."""
    return []


# ── Context builder ────────────────────────────────────────────────────────────
async def build_chat_context(
    message: str,
    project_id: str | None,
    user_id: str,
    mongo_db: Any = None,
    redis_client: Any = None,
    pg_session: Any = None,
    chroma_client: Any = None,
) -> dict:
    intent = classify_intent(message)
    context: dict[str, Any] = {
        "timestamp": datetime.utcnow().isoformat(),
        "user_question": message,
        "intent": intent,
    }

    # Load chatbot context weights from disk (trained via analyze_conversations.py)
    weights_path = os.path.join("/app", "models", "chatbot_context_weights.json")
    if os.path.exists(weights_path):
        try:
            with open(weights_path) as f:
                weights = json.load(f)
            context["recommended_focus"] = weights.get(intent, [])
        except Exception:
            pass

    # Gather all data sources in parallel
    results = await asyncio.gather(
        get_active_incidents_summary(pg_session),
        get_latest_metrics_from_redis(redis_client),
        query_similar_incidents(message, chroma_client),
        get_repo_errors_summary(mongo_db, project_id) if project_id else _empty_list(),
        return_exceptions=True,
    )

    incidents, metrics, similar, errors = results

    context["active_incidents"] = incidents if not isinstance(incidents, Exception) else []
    context["current_metrics"] = metrics if not isinstance(metrics, Exception) else []
    context["similar_past_incidents"] = similar if not isinstance(similar, Exception) else []

    if project_id:
        context["repo_errors"] = errors if not isinstance(errors, Exception) else []

    return context


# ── Prompt builder ─────────────────────────────────────────────────────────────
def build_prompt(user_message: str, context: dict) -> str:
    sections: list[str] = []

    if context.get("active_incidents"):
        sections.append("=== ACTIVE INCIDENTS ===")
        for inc in context["active_incidents"]:
            sections.append(
                f"- [{inc.get('severity', '?')}] {inc.get('title', 'Untitled')} | "
                f"Service: {inc.get('primary_service', inc.get('affected_services', 'unknown'))} | "
                f"Since: {inc.get('detected_at', inc.get('started_at', 'unknown'))} | "
                f"Root cause: {inc.get('root_cause_summary', inc.get('root_cause', 'Under investigation'))}"
            )

    if context.get("current_metrics"):
        sections.append("\n=== CURRENT SYSTEM METRICS ===")
        for m in context["current_metrics"][:3]:
            sections.append(
                f"- CPU: {m.get('cpu_usage_percent', m.get('cpu_percent', 'N/A'))}% | "
                f"Memory: {m.get('memory_usage_percent', m.get('memory_percent', 'N/A'))}% | "
                f"Disk read: {m.get('disk_read_mbps', 'N/A')} MB/s | "
                f"Timestamp: {m.get('timestamp', 'N/A')}"
            )

    if context.get("repo_errors"):
        sections.append("\n=== REPOSITORY ERRORS FOUND ===")
        for err in context["repo_errors"]:
            sections.append(
                f"- [{err.get('severity', '?')}] {err.get('error_type', 'error')} in "
                f"{err.get('file_path', 'unknown')} line {err.get('line_number', '?')}: "
                f"{err.get('title', '')} — {err.get('description', '')}"
            )

    if context.get("similar_past_incidents"):
        sections.append("\n=== SIMILAR PAST INCIDENTS ===")
        for past in context["similar_past_incidents"]:
            meta = past.get("metadata", {})
            sections.append(
                f"- {past.get('description', '')[:200]} | "
                f"Resolved in: {meta.get('mttr_minutes', '?')} min | "
                f"Fix: {str(meta.get('remediation_steps_taken', 'N/A'))[:150]}"
            )

    context_text = (
        "\n".join(sections)
        if sections
        else "No live data available yet — connect a repository and wait for first scan."
    )

    return (
        f"{context_text}\n\n"
        f"=== USER QUESTION ===\n{user_message}\n\n"
        f"Answer based strictly on the data above. Be specific. Reference actual values."
    )


# ── Conversation history (Redis) ───────────────────────────────────────────────
async def get_conversation_history(session_id: str, redis_client: Any) -> list[dict]:
    if redis_client is None:
        return []
    try:
        raw = await redis_client.lrange(f"chatbot:history:{session_id}", 0, 11)
        return [json.loads(r) for r in raw]
    except Exception as exc:
        logger.warning("get_conversation_history_failed", error=str(exc))
        return []


async def save_conversation_turn(
    session_id: str,
    user_message: str,
    assistant_response: str,
    redis_client: Any,
) -> None:
    if redis_client is None:
        return
    try:
        turn = json.dumps({
            "user": user_message[:300],
            "assistant": assistant_response[:500],
        })
        await redis_client.lpush(f"chatbot:history:{session_id}", turn)
        await redis_client.ltrim(f"chatbot:history:{session_id}", 0, 11)
        await redis_client.expire(f"chatbot:history:{session_id}", 3600)
    except Exception as exc:
        logger.warning("save_conversation_turn_failed", error=str(exc))


def format_history(history: list[dict]) -> str:
    if not history:
        return ""
    lines = ["\n=== CONVERSATION HISTORY (do not repeat this information) ==="]
    for turn in reversed(history):
        lines.append(f"User asked: {turn.get('user', '')[:100]}")
        lines.append(f"You answered: {turn.get('assistant', '')[:200]}")
    return "\n".join(lines)


# ── Save conversation to MongoDB ───────────────────────────────────────────────
async def save_message(
    session_id: str,
    user_message: str,
    assistant_response: str,
    context: dict,
    mongo_db: Any = None,
) -> None:
    if mongo_db is None:
        return
    try:
        await mongo_db["chatbot_messages"].insert_one({
            "session_id": session_id,
            "user_message": user_message,
            "assistant_response": assistant_response,
            "intent": context.get("intent", "general"),
            "active_incidents_count": len(context.get("active_incidents", [])),
            "created_at": datetime.now(UTC),
        })
    except Exception as exc:
        logger.warning("save_message_failed", error=str(exc))


# ── JWT token verification for WebSocket ──────────────────────────────────────
async def verify_token_for_ws(token: str, settings: Any) -> dict | None:
    """Verify a JWT token and return the decoded payload or None if invalid."""
    if not token:
        return None
    try:
        from jose import jwt as jose_jwt
        payload = jose_jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        user_id = payload.get("sub")
        if not user_id:
            return None
        return {"id": user_id, "email": payload.get("email", "")}
    except Exception:
        return None


# ── WebSocket endpoint ─────────────────────────────────────────────────────────
@router.websocket("/ws/chatbot/{session_id}")
async def chatbot_ws(
    websocket: WebSocket,
    session_id: str,
    token: str = Query(default=None),
):
    """
    Full-duplex WebSocket chatbot.
    Streams OpenRouter responses chunk-by-chunk.
    Auto-falls back to Phi-3 if OpenRouter fails.
    Sends ping every 25 seconds to keep connection alive.
    """
    from modules.api.main import (
        _mongo_db as mongo_db,
        _redis as redis_client,
        _sf as pg_session_factory,
        settings,
    )
    from shared.llm import llm_service

    # Authenticate before accepting
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return

    user = await verify_token_for_ws(token, settings)
    if not user:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await websocket.accept()

    # Keepalive ping task
    async def _ping_loop() -> None:
        while True:
            try:
                await asyncio.sleep(25)
                await websocket.send_json({"type": "ping"})
            except Exception:
                break

    ping_task = asyncio.create_task(_ping_loop())

    try:
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=300)
            except asyncio.TimeoutError:
                continue

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if msg.get("type") == "pong":
                continue

            user_message = msg.get("message", "").strip()
            project_id = msg.get("project_id")

            if not user_message:
                continue

            await websocket.send_json({"type": "typing_start"})

            # Build pg session fresh for each message — keep it alive during context build
            pg_sess = None
            if pg_session_factory is not None:
                try:
                    pg_sess = pg_session_factory()
                    # We pass the session maker; build_chat_context will use it directly
                except Exception:
                    pg_sess = None

            context = await build_chat_context(
                user_message,
                project_id,
                user["id"],
                mongo_db=mongo_db,
                redis_client=redis_client,
                pg_session=pg_sess,
            )

            # Build prompt with conversation history
            history = await get_conversation_history(session_id, redis_client)
            history_text = format_history(history)
            data_prompt = build_prompt(user_message, context)
            final_prompt = f"{history_text}\n\n{data_prompt}" if history_text else data_prompt

            await websocket.send_json({"type": "stream_start"})
            full_response = ""

            try:
                async for chunk in llm_service.stream(
                    final_prompt, CHATBOT_SYSTEM_PROMPT
                ):
                    full_response += chunk
                    await websocket.send_json({"type": "stream_chunk", "content": chunk})
                    await asyncio.sleep(0)
            except Exception as stream_err:
                logger.warning("llm_stream_error", error=str(stream_err))
                if not full_response:
                    full_response = f"LLM service error: {stream_err}. Please try again."
                    await websocket.send_json({"type": "stream_chunk", "content": full_response})

            model_used = (
                llm_service.model if llm_service.openrouter_available else "phi3:mini"
            )
            await websocket.send_json({
                "type": "stream_end",
                "full_response": full_response,
                "model_used": model_used,
            })

            # Save history to Redis and conversation to MongoDB
            await save_conversation_turn(
                session_id, user_message, full_response, redis_client
            )
            await save_message(session_id, user_message, full_response, context, mongo_db)

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error("chatbot_ws_error", error=str(exc), exc_info=True)
        try:
            await websocket.send_json({"type": "error", "message": f"Server error: {exc}"})
        except Exception:
            pass
    finally:
        ping_task.cancel()
        try:
            await ping_task
        except asyncio.CancelledError:
            pass


# ── REST fallback endpoint ─────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    project_id: str | None = None
    session_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    model_used: str
    intent: str


@router.post("/chatbot/message", response_model=ChatResponse)
async def chatbot_rest(request: ChatRequest):
    """
    REST fallback for clients that cannot maintain a WebSocket connection.
    Used automatically by the frontend if WebSocket fails to connect within 5 seconds.
    """
    from modules.api.main import (
        _mongo_db as mongo_db,
        _redis as redis_client,
    )
    from shared.llm import llm_service

    context = await build_chat_context(
        request.message,
        request.project_id,
        user_id="rest-client",
        mongo_db=mongo_db,
        redis_client=redis_client,
    )

    session_id = request.session_id or "rest-anon"
    history = await get_conversation_history(session_id, redis_client)
    history_text = format_history(history)
    data_prompt = build_prompt(request.message, context)
    final_prompt = f"{history_text}\n\n{data_prompt}" if history_text else data_prompt

    try:
        response_text = await llm_service.generate(
            final_prompt, CHATBOT_SYSTEM_PROMPT
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"LLM service unavailable: {exc}",
        )

    model_used = llm_service.model if llm_service.openrouter_available else "phi3:mini"

    await save_conversation_turn(session_id, request.message, response_text, redis_client)
    await save_message(session_id, request.message, response_text, context, mongo_db)

    return ChatResponse(
        response=response_text,
        model_used=model_used,
        intent=context.get("intent", "general"),
    )
