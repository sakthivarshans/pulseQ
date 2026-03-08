"""
modules/orchestrator/service.py
────────────────────────────────
Orchestrator main service.

Consumes AnomalyEvents from Redis Stream: intelligence.events.anomaly
Groups anomalies into incidents using AnomalyCorrelator.
Manages full incident lifecycle: DETECTED → INVESTIGATING → REMEDIATING → RESOLVED.
Triggers RCA Engine and Action Executor.
Sends notifications via PagerDuty, Slack, Jira.
Stores all incidents in PostgreSQL.
Publishes incident state changes to Redis Stream: intelligence.incidents.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import redis.asyncio as aioredis
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from modules.orchestrator.correlator import AnomalyCorrelator, ServiceDependencyGraph
from shared.config import get_settings
from shared.schemas import (
    AnomalyEvent,
    Incident,
    IncidentStatus,
    Severity,
)

logger = structlog.get_logger(__name__)
settings = get_settings()

CORRELATION_FLUSH_SECONDS = 30  # flush correlation windows every 30s


class OrchestratorService:
    """
    Main orchestration service. Lifecycle manager for all incidents.
    """

    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None
        self._engine: AsyncEngine | None = None
        self._session_factory: Any = None
        self._graph = ServiceDependencyGraph()
        self._correlator = AnomalyCorrelator(self._graph)
        self._running = False
        self._incidents_created = 0
        self._incidents_resolved = 0
        self._pending_clusters: dict[str, float] = {}  # cluster_key → last seen epoch

    async def start(self) -> None:
        try:
            self._redis = aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=10,
            )
            await self._redis.ping()

            # Ensure consumer group
            for stream in [settings.redis_stream_anomaly_events, settings.redis_stream_incidents]:
                try:
                    await self._redis.xgroup_create(stream, settings.redis_consumer_group, id="$", mkstream=True)
                except aioredis.ResponseError as e:
                    if "BUSYGROUP" not in str(e):
                        raise

            await self._load_topology()
        except Exception as exc:
            logger.warning("orchestrator_redis_unavailable_continuing", error=str(exc))
            self._redis = None

        # DB engine is created lazily on first use — don't connect at startup
        # This prevents ConnectionRefusedError floods when Docker/PostgreSQL is not running
        self._engine = None
        self._session_factory = None
        self._running = True
        logger.info("orchestrator_started")

    async def stop(self) -> None:
        self._running = False
        if self._redis:
            await self._redis.aclose()
        if self._engine:
            await self._engine.dispose()

    async def _load_topology(self) -> None:
        """Load service topology from Redis cache."""
        assert self._redis is not None
        raw = await self._redis.get("neuralops:topology:cache")
        if raw:
            topology = json.loads(raw)
            self._graph.load_from_dict(topology)
            logger.info("topology_loaded", services=len(topology))

    async def run_event_loop(self) -> None:
        """Consume AnomalyEvents and flush correlation windows.
        If Redis is unavailable, sleep in a low-CPU idle loop."""
        if self._redis is None:
            logger.warning("orchestrator_event_loop_idle_no_redis")
            while self._running:
                await asyncio.sleep(10)
            return

        consumer_name = f"orchestrator-{os.getpid()}"
        flush_task = asyncio.create_task(self._flush_loop(), name="flush-loop")

        while self._running:
            try:
                messages = await self._redis.xreadgroup(
                    groupname=settings.redis_consumer_group,
                    consumername=consumer_name,
                    streams={settings.redis_stream_anomaly_events: ">"},
                    count=50,
                    block=1000,
                )
                if not messages:
                    continue

                for _stream, events in messages:
                    for msg_id, fields in events:
                        try:
                            await self._handle_anomaly(fields)
                            await self._redis.xack(
                                settings.redis_stream_anomaly_events,
                                settings.redis_consumer_group,
                                msg_id,
                            )
                        except Exception as exc:
                            logger.error("anomaly_handling_failed", error=str(exc), msg_id=msg_id)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("orchestrator_loop_error", error=str(exc))
                await asyncio.sleep(5)

        flush_task.cancel()

    async def _handle_anomaly(self, fields: dict[str, str]) -> None:
        payload = json.loads(fields.get("payload", "{}"))
        anomaly = AnomalyEvent(**payload)

        is_new, cluster_key = self._correlator.add_anomaly(anomaly)
        self._pending_clusters[cluster_key] = datetime.now(UTC).timestamp()

        if is_new and anomaly.severity in (Severity.P1, Severity.P2):
            # For critical anomalies, create the incident immediately
            anomalies = self._correlator.flush_window(cluster_key)
            self._pending_clusters.pop(cluster_key, None)
            await self._create_incident(cluster_key, anomalies)

    async def _flush_loop(self) -> None:
        """Periodically flush correlation windows that have aged out."""
        while self._running:
            await asyncio.sleep(CORRELATION_FLUSH_SECONDS)
            now = datetime.now(UTC).timestamp()
            expired = [
                k for k, ts in self._pending_clusters.items()
                if now - ts > CORRELATION_FLUSH_SECONDS * 2
            ]
            for key in expired:
                anomalies = self._correlator.flush_window(key)
                self._pending_clusters.pop(key, None)
                if anomalies:
                    await self._create_incident(key, anomalies)

    async def _create_incident(
        self, cluster_key: str, anomalies: list[AnomalyEvent]
    ) -> str:
        """Build and store a new incident, trigger RCA and notifications."""
        incident = self._correlator.build_incident(cluster_key, anomalies)

        # Persist to DB only when available; skip gracefully if not
        if self._session_factory is None:
            try:
                self._engine = create_async_engine(settings.database_url, echo=False, pool_size=5)
                self._session_factory = sessionmaker(
                    self._engine, class_=AsyncSession, expire_on_commit=False
                )
            except Exception as exc:
                logger.warning("orchestrator_db_unavailable", error=str(exc))

        if self._session_factory:
            try:
                async with self._session_factory() as session:
                    await self._upsert_incident(session, incident)
            except Exception as exc:
                logger.warning("orchestrator_db_write_failed", error=str(exc))

        self._incidents_created += 1
        logger.info(
            "incident_created",
            incident_id=incident.incident_id,
            service=incident.primary_service,
            severity=incident.severity,
        )

        # Publish to Redis Stream
        await self._publish_incident_event(incident, "created")

        # Trigger RCA via HTTP to rca_engine service
        asyncio.create_task(self._trigger_rca(incident), name=f"rca-{incident.incident_id}")

        # Send notifications
        asyncio.create_task(self._notify_teams(incident), name=f"notify-{incident.incident_id}")

        return incident.incident_id

    async def _upsert_incident(self, session: AsyncSession, incident: Incident) -> None:
        """Insert or update incident in PostgreSQL."""
        data = incident.model_dump(mode="json")
        await session.execute(
            text("""
                INSERT INTO incidents (
                    incident_id, title, description, severity, status,
                    detected_at, primary_service, affected_services, blast_radius,
                    environment, cloud_provider, region, correlated_anomaly_ids,
                    peak_anomaly_score, ml_confidence, labels
                ) VALUES (
                    :incident_id, :title, :description, :severity, :status,
                    :detected_at, :primary_service, :affected_services::jsonb, :blast_radius::jsonb,
                    :environment, :cloud_provider, :region, :correlated_anomaly_ids::jsonb,
                    :peak_anomaly_score, :ml_confidence, :labels::jsonb
                )
                ON CONFLICT (incident_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    updated_at = NOW()
            """),
            {
                "incident_id": data["incident_id"],
                "title": data["title"],
                "description": data.get("description"),
                "severity": data["severity"],
                "status": data["status"],
                "detected_at": data["detected_at"],
                "primary_service": data["primary_service"],
                "affected_services": json.dumps(data["affected_services"]),
                "blast_radius": json.dumps(data.get("blast_radius")),
                "environment": data["environment"],
                "cloud_provider": data["cloud_provider"],
                "region": data.get("region"),
                "correlated_anomaly_ids": json.dumps(data["correlated_anomaly_ids"]),
                "peak_anomaly_score": data["peak_anomaly_score"],
                "ml_confidence": data["ml_confidence"],
                "labels": json.dumps(data.get("labels", {})),
            },
        )
        await session.commit()

    async def _publish_incident_event(self, incident: Incident, event_type: str) -> None:
        if self._redis is None:
            return  # Redis unavailable — skip pub silently
        payload = incident.model_dump(mode="json")
        await self._redis.xadd(
            settings.redis_stream_incidents,
            {
                "incident_id": incident.incident_id,
                "event_type": event_type,
                "severity": incident.severity,
                "service": incident.primary_service,
                "payload": json.dumps(payload),
            },
            maxlen=20_000,
            approximate=True,
        )

    async def _trigger_rca(self, incident: Incident) -> None:
        """HTTP call to RCA Engine module to start analysis."""
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    "http://rca_engine:8040/analyze",
                    json=incident.model_dump(mode="json"),
                )
                resp.raise_for_status()
                logger.info("rca_triggered", incident_id=incident.incident_id)
        except Exception as exc:
            logger.error("rca_trigger_failed", incident_id=incident.incident_id, error=str(exc))

    async def _notify_teams(self, incident: Incident) -> None:
        """Fire and forget: send PagerDuty + Slack + Jira notifications."""
        if settings.pagerduty_enabled:
            try:
                from integrations.pagerduty.integration import PagerDutyIntegration
                pd = PagerDutyIntegration()
                await pd.send_alert(incident)
            except Exception as exc:
                logger.warning("pagerduty_notify_failed", error=str(exc))

        if settings.slack_enabled:
            try:
                from integrations.slack.integration import SlackIntegration
                slack = SlackIntegration()
                await slack.send_alert(incident)
            except Exception as exc:
                logger.warning("slack_notify_failed", error=str(exc))

        if settings.jira_enabled and incident.severity in (Severity.P1, Severity.P2):
            try:
                from integrations.jira.integration import JiraIntegration
                jira = JiraIntegration()
                await jira.create_ticket(incident, incident.title)
            except Exception as exc:
                logger.warning("jira_ticket_failed", error=str(exc))

    async def update_incident_status(
        self,
        incident_id: str,
        status: IncidentStatus,
        resolved_by: str | None = None,
    ) -> None:
        """Transition an incident to a new lifecycle status."""
        if self._session_factory is None:
            logger.warning("update_incident_status_skipped_no_db", incident_id=incident_id)
            return
        now = datetime.now(UTC)
        field_map = {
            IncidentStatus.INVESTIGATING: "investigating_at",
            IncidentStatus.REMEDIATING: "remediating_at",
            IncidentStatus.RESOLVED: "resolved_at",
            IncidentStatus.POST_MORTEM: "post_mortem_at",
        }
        ts_field = field_map.get(status)
        async with self._session_factory() as session:
            update_parts = ["status = :status", "updated_at = NOW()"]
            params: dict[str, Any] = {"status": status.value, "incident_id": incident_id}
            if ts_field:
                update_parts.append(f"{ts_field} = :ts")
                params["ts"] = now
            if resolved_by:
                update_parts.append("acknowledged_by = :ack")
                params["ack"] = resolved_by
            if status == IncidentStatus.RESOLVED:
                # Calculate MTTR
                update_parts.append("mttr_minutes = EXTRACT(EPOCH FROM (NOW() - detected_at)) / 60")
                self._incidents_resolved += 1
            await session.execute(
                text(f"UPDATE incidents SET {', '.join(update_parts)} WHERE incident_id = :incident_id"),
                params,
            )
            await session.commit()
        logger.info("incident_status_updated", incident_id=incident_id, status=status)

    def get_stats(self) -> dict[str, Any]:
        return {
            "incidents_created": self._incidents_created,
            "incidents_resolved": self._incidents_resolved,
            "pending_correlation_windows": len(self._pending_clusters),
        }
