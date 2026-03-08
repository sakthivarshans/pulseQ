"""
modules/memory/store.py
────────────────────────
ChromaDB-backed vector memory store for NeuralOps self-learning.

Stores:
  - Past incidents with RCA summaries as searchable documents
  - Successful remediation actions
  - Alert runbook embeddings

Enables:
  - Similarity search for "have we seen this before?" during RCA
  - Feedback-loop: marks proven resolutions as high-quality
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import chromadb
import structlog
from chromadb.config import Settings as ChromaSettings

from shared.config import get_settings
from shared.interfaces import MemoryStoreInterface
from shared.schemas import Incident

logger = structlog.get_logger(__name__)
settings = get_settings()


class ChromaMemoryStore(MemoryStoreInterface):
    """
    ChromaDB-based vector store for self-learning memory.
    Uses all-MiniLM-L6-v2 (via chromadb's default embedding) or
    Google Gemini embedding API when available.
    """

    INCIDENTS_COLLECTION = "neuralops_incidents"
    RUNBOOKS_COLLECTION = "neuralops_runbooks"
    ACTIONS_COLLECTION = "neuralops_actions"

    def __init__(self) -> None:
        try:
            self._client = chromadb.HttpClient(
                host=settings.chromadb_host,
                port=settings.chromadb_port,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            self._incidents = self._client.get_or_create_collection(
                name=self.INCIDENTS_COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )
            self._runbooks = self._client.get_or_create_collection(
                name=self.RUNBOOKS_COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )
            self._actions = self._client.get_or_create_collection(
                name=self.ACTIONS_COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )
            self._available = True
            logger.info("chroma_memory_initialized", host=settings.chromadb_host)
        except Exception as exc:
            logger.warning("chroma_unavailable_using_noop", error=str(exc))
            self._client = None
            self._incidents = None
            self._runbooks = None
            self._actions = None
            self._available = False

    async def store_incident(
        self,
        incident: Incident,
        rca_summary: str | None = None,
        resolution_summary: str | None = None,
    ) -> str:
        """
        Store a resolved incident in vector memory.
        Complies with MemoryStoreInterface.
        """
        document = f"Incident: {incident.title}\n"
        if rca_summary:
            document += f"RCA: {rca_summary}\n"
        if resolution_summary:
            document += f"Resolution: {resolution_summary}\n"
        
        metadata = {
            "incident_id": str(incident.incident_id),
            "title": incident.title,
            "severity": incident.severity,
            "primary_service": incident.primary_service,
            "detected_at": incident.detected_at.isoformat(),
        }
        return await self._store_incident_raw(str(incident.incident_id), document, metadata)

    async def _store_incident_raw(
        self,
        incident_id: str,
        document: str,
        metadata: dict[str, Any],
    ) -> str:
        """Internal helper for raw storage."""
        doc_id = f"incident_{incident_id}"
        metadata["stored_at"] = datetime.now(UTC).isoformat()
        metadata["quality_score"] = metadata.get("quality_score", 0.5)
        self._incidents.upsert(
            documents=[document],
            metadatas=[metadata],
            ids=[doc_id],
        )
        logger.info("incident_stored", doc_id=doc_id)
        return doc_id

    async def find_similar_incidents(
        self,
        query_text: str,
        n_results: int = 5,
        min_similarity: float = 0.6,
    ) -> list[dict[str, Any]]:
        """
        Find the most semantically similar past incidents.
        Complies with MemoryStoreInterface.
        """
        return await self.search_similar_incidents(query_text, n_results, min_similarity)

    async def search_similar_incidents(
        self,
        query: str,
        n_results: int = 5,
        min_similarity: float = 0.3,
    ) -> list[dict[str, Any]]:
        """
        Vector similarity search over stored incidents.
        Returns list of matches sorted by similarity.
        """
        if self._incidents.count() == 0:
            return []
        results = self._incidents.query(
            query_texts=[query],
            n_results=min(n_results, self._incidents.count()),
            include=["documents", "metadatas", "distances"],
        )
        matches: list[dict[str, Any]] = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            # ChromaDB cosine distance: 0 = identical, 2 = opposite
            # Convert to similarity score [0, 1]
            similarity = 1.0 - (dist / 2.0)
            if similarity >= min_similarity:
                matches.append(
                    {
                        "similarity_score": round(similarity, 4),
                        "document": doc,
                        "incident_id": meta.get("incident_id", ""),
                        "title": meta.get("title", "Unknown incident"),
                        "severity": meta.get("severity", "P3"),
                        "primary_service": meta.get("primary_service", ""),
                        "root_cause_summary": meta.get("root_cause_summary", doc[:200]),
                        "detected_at": meta.get("detected_at", ""),
                        "mttr_minutes": meta.get("mttr_minutes"),
                        "quality_score": meta.get("quality_score", 0.5),
                    }
                )
        return sorted(matches, key=lambda x: x["similarity_score"], reverse=True)

    async def store_runbook(
        self,
        runbook_id: str,
        title: str,
        content: str,
        tags: list[str],
    ) -> str:
        """Store or update a runbook for semantic search."""
        doc_id = f"runbook_{runbook_id}"
        self._runbooks.upsert(
            documents=[content],
            metadatas=[{"title": title, "tags": json.dumps(tags), "runbook_id": runbook_id}],
            ids=[doc_id],
        )
        return doc_id

    async def search_runbooks(self, query: str, n_results: int = 3) -> list[dict[str, Any]]:
        """Search runbooks by semantic similarity."""
        if self._runbooks.count() == 0:
            return []
        results = self._runbooks.query(
            query_texts=[query],
            n_results=min(n_results, self._runbooks.count()),
            include=["documents", "metadatas", "distances"],
        )
        return [
            {
                "runbook_id": meta.get("runbook_id"),
                "title": meta.get("title"),
                "content": doc[:500],
                "similarity": round(1.0 - dist / 2.0, 4),
            }
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            )
        ]

    async def store_successful_action(
        self, audit_record: dict[str, Any]
    ) -> str:
        """Store a successful action execution for learning."""
        doc_id = f"action_{audit_record.get('action_id', uuid.uuid4())}"
        description = (
            f"Action: {audit_record.get('action_type')} "
            f"for incident {audit_record.get('incident_id')}. "
            f"Result: {audit_record.get('output', '')[:300]}"
        )
        self._actions.upsert(
            documents=[description],
            metadatas=[{
                "action_type": str(audit_record.get("action_type", "")),
                "incident_id": str(audit_record.get("incident_id", "")),
                "status": str(audit_record.get("status", "")),
                "duration_seconds": float(audit_record.get("duration_seconds", 0)),
            }],
            ids=[doc_id],
        )
        return doc_id

    async def update_outcome(
        self,
        incident_id: str,
        outcome: str,  # "resolved" | "escalated" | "false_positive"
        resolution_summary: str | None = None,
        mttr_minutes: float | None = None,
    ) -> None:
        """Update the stored outcome for a previously indexed incident."""
        is_false_positive = (outcome == "false_positive")
        await self.apply_feedback(incident_id, is_false_positive, mttr_minutes)

    async def apply_feedback(
        self, incident_id: str, is_false_positive: bool, actual_mttr_minutes: float | None = None
    ) -> None:
        """Update stored incident quality score based on feedback."""
        doc_id = f"incident_{incident_id}"
        try:
            existing = self._incidents.get(ids=[doc_id], include=["metadatas", "documents"])
            if existing["ids"]:
                meta = existing["metadatas"][0]
                doc = existing["documents"][0]
                meta["is_false_positive"] = is_false_positive
                meta["quality_score"] = 0.1 if is_false_positive else 0.9
                if actual_mttr_minutes is not None:
                    meta["mttr_minutes"] = actual_mttr_minutes
                self._incidents.upsert(documents=[doc], metadatas=[meta], ids=[doc_id])
                logger.info("feedback_applied", incident_id=incident_id)
        except Exception as exc:
            logger.warning("feedback_apply_failed", incident_id=incident_id, error=str(exc))

    async def get_training_data(
        self,
        lookback_days: int = 7,
    ) -> list[dict[str, Any]]:
        """Retrieve recent resolved incidents as training feature vectors."""
        # For now, return all incidents as we don't have time filtering in Chroma easily
        if self._incidents.count() == 0:
            return []
        
        results = self._incidents.get(include=["metadatas", "documents"])
        training_data = []
        for doc, meta in zip(results["documents"], results["metadatas"]):
            training_data.append({
                "document": doc,
                "metadata": meta,
            })
        return training_data

    def get_stats(self) -> dict[str, int]:
        return {
            "incidents_stored": self._incidents.count(),
            "runbooks_stored": self._runbooks.count(),
            "actions_stored": self._actions.count(),
        }
