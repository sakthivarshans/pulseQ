"""
integrations/pagerduty/integration.py
───────────────────────────────────────
PagerDuty integration — creates and resolves incidents via Events API v2.
"""
from __future__ import annotations

from typing import Any
import httpx
import structlog

from shared.config import get_settings
from shared.interfaces import ToolIntegrationInterface
from shared.schemas import Incident, Severity

logger = structlog.get_logger(__name__)
settings = get_settings()

_PD_SEVERITY = {
    Severity.P1: "critical",
    Severity.P2: "error",
    Severity.P3: "warning",
    Severity.P4: "info",
}


class PagerDutyIntegration(ToolIntegrationInterface):

    _EVENTS_V2_URL = "https://events.pagerduty.com/v2/enqueue"

    def __init__(self) -> None:
        self._service_key = settings.pagerduty_service_key or ""
        self._api_key = settings.pagerduty_api_key or ""
        self._base_url = "https://api.pagerduty.com"

    async def send_alert(self, incident: Incident) -> str | None:
        """Trigger a PagerDuty incident. Returns dedup_key."""
        dedup_key = f"neuralops-{incident.incident_id}"
        payload = {
            "routing_key": self._service_key,
            "event_action": "trigger",
            "dedup_key": dedup_key,
            "payload": {
                "summary": f"[{incident.severity}] {incident.title}",
                "severity": _PD_SEVERITY.get(incident.severity, "warning"),
                "source": incident.primary_service,
                "timestamp": incident.detected_at.isoformat(),
                "custom_details": {
                    "affected_services": incident.affected_services,
                    "environment": incident.environment,
                    "peak_anomaly_score": incident.peak_anomaly_score,
                    "ml_confidence": incident.ml_confidence,
                    "incident_id": incident.incident_id,
                },
            },
            "links": [
                {
                    "href": f"{settings.api_base_url}/incidents/{incident.incident_id}",
                    "text": "View in NeuralOps Dashboard",
                }
            ],
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(self._EVENTS_V2_URL, json=payload)
            resp.raise_for_status()
            logger.info("pagerduty_alert_sent", dedup_key=dedup_key)
            return dedup_key

    async def resolve_incident(self, dedup_key: str) -> bool:
        """Resolve a PagerDuty incident by dedup key."""
        payload = {
            "routing_key": self._service_key,
            "event_action": "resolve",
            "dedup_key": dedup_key,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(self._EVENTS_V2_URL, json=payload)
            resp.raise_for_status()
        return True

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{self._base_url}/abilities",
                    headers={"Authorization": f"Token token={self._api_key}"},
                )
                return resp.status_code == 200
        except Exception:
            return False

    async def execute_action(self, action_type: str, parameters: dict[str, Any]) -> dict[str, Any]:
        dedup_key = parameters.get("dedup_key", "")
        if action_type == "resolve":
            await self.resolve_incident(dedup_key)
            return {"status": "resolved", "dedup_key": dedup_key}
        return {"error": f"Unknown action: {action_type}"}

    async def get_status(self) -> dict[str, Any]:
        healthy = await self.health_check()
        return {"integration": "pagerduty", "healthy": healthy}
