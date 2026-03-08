"""
integrations/jira/integration.py
──────────────────────────────────
Jira integration — creates tickets for P1/P2 incidents via Jira REST API.
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

_JIRA_PRIORITY = {
    Severity.P1: "Highest",
    Severity.P2: "High",
    Severity.P3: "Medium",
    Severity.P4: "Low",
}


class JiraIntegration(ToolIntegrationInterface):

    def __init__(self) -> None:
        self._base_url = (settings.jira_base_url or "").rstrip("/")
        self._email = settings.jira_user_email or ""
        self._api_token = settings.jira_api_token or ""
        self._project_key = settings.jira_project_key or "OPS"
        self._auth = (self._email, self._api_token)

    async def create_ticket(self, incident: Incident, description: str | None = None) -> str:
        """Create a Jira issue for the incident. Returns issue key (e.g., OPS-123)."""
        rca_link = f"{settings.api_base_url}/incidents/{incident.incident_id}"
        body = description or (
            f"*Incident*: {incident.title}\n"
            f"*Severity*: {incident.severity}\n"
            f"*Primary Service*: {incident.primary_service}\n"
            f"*Affected Services*: {', '.join(incident.affected_services)}\n"
            f"*Environment*: {incident.environment}\n"
            f"*Detected At*: {incident.detected_at.isoformat()}\n"
            f"*NeuralOps Link*: {rca_link}\n\n"
            f"_This ticket was automatically created by NeuralOps AI._"
        )
        payload = {
            "fields": {
                "project": {"key": self._project_key},
                "summary": f"[{incident.severity}] {incident.title[:120]}",
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": body}],
                        }
                    ],
                },
                "issuetype": {"name": "Bug"},
                "priority": {"name": _JIRA_PRIORITY.get(incident.severity, "Medium")},
                "labels": ["neuralops", "automated", incident.environment, incident.cloud_provider],
            }
        }
        async with httpx.AsyncClient(timeout=15.0, auth=self._auth) as client:
            resp = await client.post(
                f"{self._base_url}/rest/api/3/issue", json=payload
            )
            resp.raise_for_status()
            key = resp.json()["key"]
            logger.info("jira_ticket_created", key=key, incident_id=incident.incident_id)
            return key

    async def transition_ticket(self, issue_key: str, status: str) -> bool:
        """Transition a Jira ticket to a new status."""
        # Get available transitions
        async with httpx.AsyncClient(timeout=10.0, auth=self._auth) as client:
            tr_resp = await client.get(f"{self._base_url}/rest/api/3/issue/{issue_key}/transitions")
            tr_resp.raise_for_status()
            transitions = {t["name"]: t["id"] for t in tr_resp.json().get("transitions", [])}
            target_id = transitions.get(status)
            if not target_id:
                logger.warning("jira_transition_not_found", issue=issue_key, status=status)
                return False
            tr_do = await client.post(
                f"{self._base_url}/rest/api/3/issue/{issue_key}/transitions",
                json={"transition": {"id": target_id}},
            )
            tr_do.raise_for_status()
        return True

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0, auth=self._auth) as client:
                resp = await client.get(f"{self._base_url}/rest/api/3/myself")
                return resp.status_code == 200
        except Exception:
            return False

    async def send_alert(self, incident: Incident) -> str | None:
        return await self.create_ticket(incident)

    async def execute_action(self, action_type: str, parameters: dict[str, Any]) -> dict[str, Any]:
        if action_type == "create_ticket":
            from shared.schemas import Incident as Incident_
            inc = Incident_(**parameters["incident"])
            key = await self.create_ticket(inc, parameters.get("description"))
            return {"ticket_key": key}
        if action_type == "transition":
            success = await self.transition_ticket(
                parameters["issue_key"], parameters["status"]
            )
            return {"success": success}
        return {"error": f"Unknown action: {action_type}"}

    async def get_status(self) -> dict[str, Any]:
        healthy = await self.health_check()
        return {"integration": "jira", "healthy": healthy, "project": self._project_key}
