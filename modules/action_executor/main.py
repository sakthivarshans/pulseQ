"""
modules/action_executor/main.py
────────────────────────────────
FastAPI application for the Action Executor module.
Receives action requests from the Orchestrator or Dashboard API,
enforces approval workflows, and delegates to executor.py.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from modules.action_executor.executor import ActionExecutor
from shared.config import get_settings
from shared.schemas import ActionRequest

logger = structlog.get_logger(__name__)
settings = get_settings()

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

_executor: ActionExecutor | None = None
_engine = None
_session_factory = None


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    global _executor, _engine, _session_factory
    _engine = create_async_engine(settings.database_url, echo=False, pool_size=5)
    _session_factory = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    
    _executor = ActionExecutor(session_factory=_session_factory)
    # ActionExecutor.start() doesn't exist in the implementation, removing it
    logger.info("action_executor_ready")
    yield
    await _engine.dispose()


app = FastAPI(
    title="NeuralOps Action Executor",
    version="1.0.0",
    description="Safe, auditable automated remediation executor",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "module": "action_executor"}


@app.post("/execute", status_code=202)
async def execute_action(request: ActionRequest) -> dict[str, Any]:
    """
    Execute a remediation action.
    Returns immediately with audit record — actual execution may be async.
    """
    if _executor is None:
        raise HTTPException(503, "Executor not ready")
    result = await _executor.execute(request)
    return result.model_dump(mode="json")


@app.get("/audit/{action_id}")
async def get_audit(action_id: str) -> dict[str, Any]:
    """Retrieve audit record for a specific action."""
    if _executor is None:
        raise HTTPException(503)
    record = await _executor.get_audit_record(action_id)
    if not record:
        raise HTTPException(404, "Action not found")
    return record.model_dump(mode="json")


if __name__ == "__main__":
    uvicorn.run(
        "modules.action_executor.main:app",
        host=settings.api_host,
        port=8050,
        reload=False,
    )
