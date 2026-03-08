"""
modules/rca_engine/main.py
───────────────────────────
FastAPI application for the RCA Engine.
Endpoint: POST /analyze — triggered by Orchestrator to start RCA for an incident.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as aioredis
import structlog
import uvicorn
from fastapi import FastAPI, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from modules.rca_engine.analyzer import RCAAnalyzer
from modules.rca_engine.context_builder import RCAContextBuilder
from shared.config import get_settings
from shared.schemas import Incident, RCAResult

logger = structlog.get_logger(__name__)
settings = get_settings()

_redis: aioredis.Redis | None = None
_engine = None
_session_factory = None


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    global _redis, _engine, _session_factory
    try:
        _redis = aioredis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
        await _redis.ping()
        logger.info("rca_engine_redis_connected")
    except Exception as exc:
        logger.warning("rca_engine_redis_unavailable", error=str(exc))
        _redis = None
    _engine = create_async_engine(settings.database_url, echo=False, pool_size=5)
    _session_factory = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    logger.info("rca_engine_ready")
    yield
    if _redis:
        await _redis.aclose()
    await _engine.dispose()


app = FastAPI(
    title="NeuralOps RCA Engine",
    version="1.0.0",
    description="LLM-powered root cause analysis for incidents",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "module": "rca_engine"}


@app.post("/analyze", response_model=RCAResult, status_code=status.HTTP_200_OK)
async def analyze_incident(incident: Incident) -> RCAResult:
    """
    Perform root cause analysis for the given incident.
    Called by the Orchestrator. Returns the full RCAResult.
    """
    if _session_factory is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    try:
        async with _session_factory() as session:
            context_builder = RCAContextBuilder(redis=_redis)
            analyzer = RCAAnalyzer(context_builder=context_builder, session=session)
            result = await analyzer.analyze(incident)
        return result
    except Exception as exc:
        logger.error("rca_analysis_failed", incident_id=incident.incident_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"RCA analysis failed: {exc}") from exc


@app.get("/rca/{incident_id}")
async def get_rca(incident_id: str) -> dict[str, Any]:
    """Retrieve stored RCA result for an incident."""
    if _session_factory is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    from sqlalchemy import text
    async with _session_factory() as session:
        result = await session.execute(
            text("SELECT * FROM rca_results WHERE incident_id = :iid LIMIT 1"),
            {"iid": incident_id},
        )
        row = result.mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="RCA not found")
        return dict(row)


if __name__ == "__main__":
    uvicorn.run("modules.rca_engine.main:app", host=settings.api_host, port=8040, reload=False)
