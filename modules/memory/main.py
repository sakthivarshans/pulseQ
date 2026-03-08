"""
modules/memory/main.py
───────────────────────
FastAPI application for the Memory module.
Exposes HTTP API used by other modules to store/search incidents and runbooks.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from modules.memory.store import ChromaMemoryStore
from shared.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

_store: ChromaMemoryStore | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    global _store
    _store = ChromaMemoryStore()
    logger.info("memory_module_ready")
    yield


app = FastAPI(
    title="NeuralOps Memory",
    version="1.0.0",
    description="ChromaDB-backed self-learning memory store",
    lifespan=lifespan,
)


class StoreRequest(BaseModel):
    incident_id: str
    document: str
    metadata: dict = {}


class SearchRequest(BaseModel):
    query: str
    n_results: int = 5
    min_similarity: float = 0.3


class FeedbackRequest(BaseModel):
    incident_id: str
    is_false_positive: bool
    actual_mttr_minutes: float | None = None


@app.get("/health")
async def health():
    if _store is None:
        raise HTTPException(status_code=503)
    return {"status": "ok", "module": "memory", "stats": _store.get_stats()}


@app.post("/store", status_code=201)
async def store_incident(req: StoreRequest) -> dict:
    if _store is None:
        raise HTTPException(503)
    doc_id = await _store._store_incident_raw(req.incident_id, req.document, req.metadata)
    return {"doc_id": doc_id}


@app.post("/search")
async def search_similar(req: SearchRequest) -> dict:
    if _store is None:
        raise HTTPException(503)
    results = await _store.search_similar_incidents(
        req.query, req.n_results, req.min_similarity
    )
    return {"results": results, "total": len(results)}


@app.post("/feedback")
async def apply_feedback(req: FeedbackRequest) -> dict:
    if _store is None:
        raise HTTPException(503)
    await _store.apply_feedback(
        req.incident_id, req.is_false_positive, req.actual_mttr_minutes
    )
    return {"status": "ok"}


@app.post("/runbook/store", status_code=201)
async def store_runbook(payload: dict) -> dict:
    if _store is None:
        raise HTTPException(503)
    doc_id = await _store.store_runbook(
        runbook_id=payload["runbook_id"],
        title=payload["title"],
        content=payload["content"],
        tags=payload.get("tags", []),
    )
    return {"doc_id": doc_id}


@app.post("/runbook/search")
async def search_runbooks(req: SearchRequest) -> dict:
    if _store is None:
        raise HTTPException(503)
    results = await _store.search_runbooks(req.query, req.n_results)
    return {"results": results}


if __name__ == "__main__":
    uvicorn.run("modules.memory.main:app", host=settings.api_host, port=8060, reload=False)
