"""
modules/ingestion/main.py
──────────────────────────
FastAPI application for the Ingestion Engine.
Exposes:
  - /health — liveness/readiness probe
  - /metrics — ingestion rate counters (Prometheus format)
  - /events  — HTTP push endpoint for OTel-forwarded events
  - /otel/metrics, /otel/logs, /otel/traces — normalized OTel receivers
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST

from modules.ingestion.service import IngestionService
from shared.config import get_settings
from shared.schemas import IntelligenceEvent

logger = structlog.get_logger(__name__)
settings = get_settings()

# ── Prometheus metrics ────────────────────────────────────────────────────────
EVENTS_INGESTED = Counter(
    "neuralops_ingestion_events_total",
    "Total events ingested",
    ["event_type", "source"],
)
EVENTS_ERRORS = Counter(
    "neuralops_ingestion_errors_total",
    "Total ingestion errors",
    ["error_type"],
)
EVENTS_DEDUPLICATED = Counter(
    "neuralops_ingestion_deduplicated_total",
    "Total duplicate events dropped",
)
ACTIVE_CONNECTORS = Gauge(
    "neuralops_ingestion_active_connectors",
    "Number of active cloud connectors",
)

# ── Global service instance ────────────────────────────────────────────────────
_ingestion_service: IngestionService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    global _ingestion_service
    _ingestion_service = IngestionService()
    await _ingestion_service.start()
    ACTIVE_CONNECTORS.set(len(_ingestion_service._connectors))

    # Run collection loop as background task
    collection_task = asyncio.create_task(
        _ingestion_service.run_collection_loop(),
        name="collection-loop",
    )
    logger.info("ingestion_app_ready")
    yield
    collection_task.cancel()
    try:
        await collection_task
    except asyncio.CancelledError:
        pass
    await _ingestion_service.stop()


app = FastAPI(
    title="NeuralOps Ingestion Engine",
    version="1.0.0",
    description="Normalizes and ingests telemetry from all cloud providers and OTel sources",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins or ["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── Health ────────────────────────────────────────────────────────────────────


@app.get("/health", tags=["observability"])
async def health() -> dict[str, Any]:
    """Liveness and readiness probe."""
    if _ingestion_service is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    stats = _ingestion_service.get_stats()
    return {
        "status": "ok",
        "module": "ingestion",
        "stats": stats,
    }


# ── Prometheus metrics endpoint ───────────────────────────────────────────────


@app.get("/metrics", response_class=PlainTextResponse, tags=["observability"])
async def prometheus_metrics() -> str:
    """Expose Prometheus-format metrics."""
    return generate_latest().decode("utf-8")


# ── HTTP push endpoint for OTel-forwarded raw events ─────────────────────────


@app.post(
    "/events",
    status_code=status.HTTP_202_ACCEPTED,
    tags=["ingestion"],
)
async def push_events(events: list[IntelligenceEvent]) -> dict[str, int]:
    """
    Accept a batch of pre-normalized IntelligenceEvents via HTTP.
    Used by OTel Collector exporter and direct integrations.
    """
    if not _ingestion_service:
        raise HTTPException(status_code=503, detail="Service not ready")
    published = await _ingestion_service.publish_events(events)
    for ev in events[:published]:
        EVENTS_INGESTED.labels(event_type=ev.event_type, source=ev.source).inc()
    return {"published": published, "received": len(events)}


# ── OTel normalized receivers ─────────────────────────────────────────────────


@app.post("/otel/metrics", status_code=202, tags=["ingestion"])
async def receive_otel_metrics(request: Request) -> dict[str, str]:
    """
    Receive pre-parsed OTel metric payloads from the collector.
    The OTel collector normalizes to IntelligenceEvent format before forwarding.
    """
    if not _ingestion_service:
        raise HTTPException(status_code=503, detail="Service not ready")
    body = await request.json()
    events = [IntelligenceEvent(**e) for e in body.get("events", [])]
    published = await _ingestion_service.publish_events(events)
    for ev in events[:published]:
        EVENTS_INGESTED.labels(event_type=ev.event_type, source=ev.source).inc()
    return {"status": "accepted", "published": str(published)}


@app.post("/otel/logs", status_code=202, tags=["ingestion"])
async def receive_otel_logs(request: Request) -> dict[str, str]:
    """Receive OTel log records normalized to IntelligenceEvent."""
    if not _ingestion_service:
        raise HTTPException(status_code=503, detail="Service not ready")
    body = await request.json()
    events = [IntelligenceEvent(**e) for e in body.get("events", [])]
    published = await _ingestion_service.publish_events(events)
    for ev in events[:published]:
        EVENTS_INGESTED.labels(event_type=ev.event_type, source=ev.source).inc()
    return {"status": "accepted", "published": str(published)}


@app.post("/otel/traces", status_code=202, tags=["ingestion"])
async def receive_otel_traces(request: Request) -> dict[str, str]:
    """Receive OTel trace spans normalized to IntelligenceEvent."""
    if not _ingestion_service:
        raise HTTPException(status_code=503, detail="Service not ready")
    body = await request.json()
    events = [IntelligenceEvent(**e) for e in body.get("events", [])]
    published = await _ingestion_service.publish_events(events)
    for ev in events[:published]:
        EVENTS_INGESTED.labels(event_type=ev.event_type, source=ev.source).inc()
    return {"status": "accepted", "published": str(published)}


if __name__ == "__main__":
    uvicorn.run(
        "modules.ingestion.main:app",
        host=settings.api_host,
        port=8010,
        log_level=settings.api_log_level,
        reload=False,
    )
