"""
modules/orchestrator/main.py
──────────────────────────────
FastAPI application for the Orchestrator.
Maintains the event consumption and correlation loop as a background task.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException

from modules.orchestrator.service import OrchestratorService
from shared.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

_orchestrator: OrchestratorService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    global _orchestrator
    _orchestrator = OrchestratorService()
    await _orchestrator.start()
    
    # Run event loop as background task
    event_task = asyncio.create_task(
        _orchestrator.run_event_loop(),
        name="orchestrator-event-loop",
    )
    logger.info("orchestrator_ready")
    yield
    event_task.cancel()
    try:
        await event_task
    except asyncio.CancelledError:
        pass
    await _orchestrator.stop()


app = FastAPI(
    title="NeuralOps Orchestrator",
    version="1.0.0",
    description="Incident lifecycle manager and anomaly correlator",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, Any]:
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    return {
        "status": "ok",
        "module": "orchestrator",
        "stats": _orchestrator.get_stats(),
    }


if __name__ == "__main__":
    uvicorn.run(
        "modules.orchestrator.main:app",
        host=settings.api_host,
        port=8030,
        log_level=settings.api_log_level,
        reload=False,
    )
