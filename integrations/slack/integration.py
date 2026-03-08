"""
integrations/slack/integration.py
───────────────────────────────────
Slack integration implementing ToolIntegrationInterface.
Sends structured incident alerts and thread-based updates.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from slack_sdk.web.async_client import AsyncWebClient

from shared.config import get_settings
from shared.interfaces import ToolIntegrationInterface
from shared.schemas import Incident, RCAResult, Severity

logger = structlog.get_logger(__name__)
settings = get_settings()

_SEVERITY_COLORS = {
    Severity.P1: "#FF0000",
    Severity.P2: "#FF8C00",
    Severity.P3: "#FFA500",
    Severity.P4: "#2196F3",
}
_SEVERITY_EMOJI = {
    Severity.P1: ":red_circle:",
    Severity.P2: ":large_orange_circle:",
    Severity.P3: ":large_yellow_circle:",
    Severity.P4: ":large_blue_circle:",
}


class SlackIntegration(ToolIntegrationInterface):

    def __init__(self) -> None:
        self._client = AsyncWebClient(token=settings.slack_bot_token)
        self._alerts_channel = settings.slack_alerts_channel or "#neuralops-alerts"

    async def send_alert(self, incident: Incident) -> str | None:
        """Send an incident alert to Slack. Returns thread timestamp."""
        emoji = _SEVERITY_EMOJI.get(incident.severity, ":warning:")
        color = _SEVERITY_COLORS.get(incident.severity, "#FFA500")
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"{emoji} [{incident.severity}] {incident.title}"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Service:*\n{incident.primary_service}"},
                    {"type": "mrkdwn", "text": f"*Environment:*\n{incident.environment}"},
                    {"type": "mrkdwn", "text": f"*Affected Services:*\n{', '.join(incident.affected_services[:5])}"},
                    {"type": "mrkdwn", "text": f"*ML Confidence:*\n{incident.ml_confidence:.0%}"},
                ],
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "🔍 View Incident"},
                        "url": f"{settings.api_base_url}/incidents/{incident.incident_id}",
                        "style": "primary",
                    }
                ],
            },
        ]
        try:
            resp = await self._client.chat_postMessage(
                channel=self._alerts_channel,
                text=f"[{incident.severity}] {incident.title}",
                blocks=blocks,
                attachments=[{"color": color}],
            )
            thread_ts = resp.get("ts")
            logger.info("slack_alert_sent", incident_id=incident.incident_id, ts=thread_ts)
            return thread_ts
        except Exception as exc:
            logger.error("slack_alert_failed", error=str(exc))
            return None

    async def send_rca_update(self, incident: Incident, rca: RCAResult, thread_ts: str) -> None:
        """Post RCA result as a thread reply to the incident alert."""
        steps_text = "\n".join(
            f"{i+1}. [{s.risk_level.upper()}] {s.action}"
            for i, s in enumerate(rca.remediation_steps[:5])
        )
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*🧠 RCA Complete* (Confidence: {rca.root_cause_confidence:.0%})\n\n"
                        f"*Root Cause:* {rca.root_cause_summary}\n\n"
                        f"*Primary Factor:* {rca.primary_contributing_factor}\n\n"
                        f"*Remediation Steps:*\n{steps_text}"
                    ),
                },
            }
        ]
        try:
            await self._client.chat_postMessage(
                channel=self._alerts_channel,
                thread_ts=thread_ts,
                blocks=blocks,
                text=f"RCA: {rca.root_cause_summary[:100]}",
            )
        except Exception as exc:
            logger.error("slack_rca_update_failed", error=str(exc))

    async def health_check(self) -> bool:
        try:
            resp = await self._client.auth_test()
            return resp.get("ok", False)
        except Exception:
            return False

    async def execute_action(self, action_type: str, parameters: dict[str, Any]) -> dict[str, Any]:
        channel = parameters.get("channel", self._alerts_channel)
        message = parameters.get("message", "NeuralOps action notification")
        resp = await self._client.chat_postMessage(channel=channel, text=message)
        return {"ts": resp.get("ts"), "channel": channel}

    async def get_status(self) -> dict[str, Any]:
        healthy = await self.health_check()
        return {"integration": "slack", "healthy": healthy, "channel": self._alerts_channel}
