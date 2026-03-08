"""
modules/rca_engine/context_builder.py
───────────────────────────────────────
Builds the structured context object sent to the LLM for RCA.
Aggregates: correlated logs, metric summaries, recent deployments,
dependency graph excerpt, top-5 similar past incidents from ChromaDB,
and current infrastructure state snapshot.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import redis.asyncio as aioredis
import structlog

from shared.config import get_settings
from shared.schemas import Incident

logger = structlog.get_logger(__name__)
settings = get_settings()


class RCAContextBuilder:
    """
    Assembles the rich context payload that the RCA Engine sends to the LLM.
    """

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis

    async def build(self, incident: Incident) -> dict[str, Any]:
        """
        Build complete context for RCA. All data fetched concurrently.
        """
        import asyncio

        window_start = incident.detected_at - timedelta(minutes=30)
        window_end = incident.detected_at + timedelta(minutes=10)

        (
            logs,
            metric_summaries,
            deployments,
            similar_incidents,
            infra_state,
        ) = await asyncio.gather(
            self._fetch_logs(incident, window_start, window_end),
            self._fetch_metric_summaries(incident, window_start, window_end),
            self._fetch_recent_deployments(incident.affected_services),
            self._fetch_similar_incidents(incident),
            self._fetch_infra_state(incident),
            return_exceptions=True,
        )

        return {
            "incident": {
                "incident_id": incident.incident_id,
                "title": incident.title,
                "severity": incident.severity,
                "primary_service": incident.primary_service,
                "affected_services": incident.affected_services,
                "detected_at": incident.detected_at.isoformat(),
                "peak_anomaly_score": incident.peak_anomaly_score,
                "ml_confidence": incident.ml_confidence,
                "blast_radius": (
                    incident.blast_radius.model_dump()
                    if incident.blast_radius else {}
                ),
            },
            "correlated_logs": logs if isinstance(logs, list) else [],
            "metric_summaries": metric_summaries if isinstance(metric_summaries, dict) else {},
            "recent_deployments": deployments if isinstance(deployments, list) else [],
            "similar_past_incidents": similar_incidents if isinstance(similar_incidents, list) else [],
            "infrastructure_state": infra_state if isinstance(infra_state, dict) else {},
            "analysis_window": {
                "start": window_start.isoformat(),
                "end": window_end.isoformat(),
            },
        }

    async def _fetch_logs(
        self,
        incident: Incident,
        start: datetime,
        end: datetime,
    ) -> list[str]:
        """Fetch relevant logs from the raw events Redis stream."""
        try:
            start_ms = int(start.timestamp() * 1000)
            end_ms = int(end.timestamp() * 1000)
            raw_msgs = await self._redis.xrange(
                settings.redis_stream_raw_events,
                min=f"{start_ms}-0",
                max=f"{end_ms}-0",
                count=500,
            )
            log_lines: list[str] = []
            for _msg_id, fields in raw_msgs:
                payload = json.loads(fields.get("payload", "{}"))
                svc = payload.get("service_name", "")
                if svc not in incident.affected_services and svc != incident.primary_service:
                    continue
                if payload.get("event_type") == "log":
                    log_data = payload.get("log", {})
                    if log_data:
                        level = log_data.get("level", "INFO")
                        msg = log_data.get("message", "")
                        log_lines.append(f"[{svc}][{level}] {msg}")
            # Prioritize ERROR and FATAL logs
            errors = [l for l in log_lines if "[ERROR]" in l or "[FATAL]" in l]
            others = [l for l in log_lines if l not in errors]
            return (errors + others)[:100]  # cap at 100
        except Exception as exc:
            logger.warning("log_fetch_failed", error=str(exc))
            return []

    async def _fetch_metric_summaries(
        self,
        incident: Incident,
        start: datetime,
        end: datetime,
    ) -> dict[str, Any]:
        """Compute metric statistics from the raw events stream."""
        try:
            start_ms = int(start.timestamp() * 1000)
            end_ms = int(end.timestamp() * 1000)
            raw_msgs = await self._redis.xrange(
                settings.redis_stream_raw_events,
                min=f"{start_ms}-0",
                max=f"{end_ms}-0",
                count=2000,
            )
            stats: dict[str, dict[str, list[float]]] = {}
            for _msg_id, fields in raw_msgs:
                payload = json.loads(fields.get("payload", "{}"))
                if payload.get("event_type") != "metric":
                    continue
                svc = payload.get("service_name", "")
                if svc not in incident.affected_services and svc != incident.primary_service:
                    continue
                metric_data = payload.get("metric", {})
                if not metric_data:
                    continue
                mtype = metric_data.get("metric_type", "unknown")
                value = metric_data.get("value", 0.0)
                if svc not in stats:
                    stats[svc] = {}
                if mtype not in stats[svc]:
                    stats[svc][mtype] = []
                stats[svc][mtype].append(float(value))

            # Compute summary statistics
            summaries: dict[str, Any] = {}
            for svc, metrics in stats.items():
                summaries[svc] = {}
                for mtype, values in metrics.items():
                    if values:
                        summaries[svc][mtype] = {
                            "min": round(min(values), 4),
                            "max": round(max(values), 4),
                            "avg": round(sum(values) / len(values), 4),
                            "last": round(values[-1], 4),
                            "count": len(values),
                        }
            return summaries
        except Exception as exc:
            logger.warning("metric_summary_failed", error=str(exc))
            return {}

    async def _fetch_recent_deployments(
        self, service_names: list[str]
    ) -> list[dict[str, Any]]:
        """Fetch recent deployments from configured DevOps integrations."""
        deployments: list[dict[str, Any]] = []
        try:
            if settings.github_enabled:
                from integrations.github.integration import GitHubIntegration
                gh = GitHubIntegration()
                deploys = await gh.get_recent_deployments(
                    service_names=service_names, lookback_hours=24
                )
                deployments.extend([d.model_dump() for d in deploys])
        except Exception as exc:
            logger.warning("github_deployments_failed", error=str(exc))
        try:
            if settings.jenkins_enabled:
                from integrations.jenkins.integration import JenkinsIntegration
                jenkins = JenkinsIntegration()
                deploys = await jenkins.get_recent_deployments(
                    service_names=service_names, lookback_hours=24
                )
                deployments.extend([d.model_dump() for d in deploys])
        except Exception as exc:
            logger.warning("jenkins_deployments_failed", error=str(exc))
        return deployments[:20]

    async def _fetch_similar_incidents(self, incident: Incident) -> list[dict[str, Any]]:
        """Query ChromaDB via Memory module HTTP API."""
        try:
            query = f"{incident.primary_service} severity={incident.severity} services={','.join(incident.affected_services)}"
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    "http://memory:8060/search",
                    json={"query": query, "n_results": 5},
                )
                if resp.status_code == 200:
                    return resp.json().get("results", [])
        except Exception as exc:
            logger.warning("similar_incident_fetch_failed", error=str(exc))
        return []

    async def _fetch_infra_state(self, incident: Incident) -> dict[str, Any]:
        """Retrieve current infra state from enabled cloud connectors."""
        state: dict[str, Any] = {"cloud_provider": incident.cloud_provider}
        try:
            if settings.aws_enabled:
                from connectors.aws.collector import AWSCollector
                conn = AWSCollector()
                inventory = await conn.get_resource_inventory()
                state["aws_resources"] = inventory[:20]
        except Exception as exc:
            logger.warning("aws_state_failed", error=str(exc))
        return state
