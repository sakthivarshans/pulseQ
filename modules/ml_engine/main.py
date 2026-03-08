"""
modules/ml_engine/main.py
──────────────────────────
FastAPI application for the ML Engine.
Maintains the anomaly detection loop as a background task.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException

from modules.ml_engine.detector import AnomalyDetectorService
from shared.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

_ml_service: AnomalyDetectorService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    global _ml_service
    _ml_service = AnomalyDetectorService()
    await _ml_service.start()
    
    # Run detection loop as background task
    detection_task = asyncio.create_task(
        _ml_service.run_detection_loop(),
        name="ml-detection-loop",
    )
    logger.info("ml_engine_ready")
    yield
    detection_task.cancel()
    try:
        await detection_task
    except (asyncio.CancelledError, AssertionError):
        pass
    await _ml_service.stop()


app = FastAPI(
    title="NeuralOps ML Engine",
    version="1.0.0",
    description="Real-time hybrid anomaly detection (LSTM + Isolation Forest)",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, Any]:
    if _ml_service is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    return {
        "status": "ok",
        "module": "ml_engine",
        "stats": _ml_service.get_stats(),
    }


if __name__ == "__main__":
    uvicorn.run(
        "modules.ml_engine.main:app",
        host=settings.api_host,
        port=8020,
        log_level=settings.api_log_level,
        reload=False,
    )
