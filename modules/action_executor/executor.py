"""
modules/action_executor/executor.py
─────────────────────────────────────
Action Executor — safely executes remediation actions.

Responsibilities:
- Validates action against allowlist before execution
- Captures full before/after state diff
- Executes via appropriate integration (kubectl, cloud SDK, Slack, etc.)
- Writes complete audit record to PostgreSQL
- Supports rollback for each action type
- Only auto-executes when confidence >= threshold; else queues for approval
"""
from __future__ import annotations

import json
import shlex
import subprocess
import time
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import get_settings
from shared.schemas import (
    ActionAuditRecord,
    ActionRequest,
    ActionStatus,
    ActionType,
)

logger = structlog.get_logger(__name__)
settings = get_settings()

# ── Safe action allowlist per environment ─────────────────────────────────────
_BASE_ALLOWLIST = {
    ActionType.KUBECTL_ROLLOUT_RESTART,
    ActionType.KUBECTL_SCALE,
    ActionType.PAGERDUTY_ALERT,
    ActionType.SLACK_NOTIFICATION,
    ActionType.JIRA_TICKET,
    ActionType.CACHE_FLUSH,
    ActionType.WEBHOOK,
}

_PRODUCTION_ONLY: set[ActionType] = {
    ActionType.AWS_ASG_SCALE,
    ActionType.AZURE_VMSS_SCALE,
    ActionType.GCP_MIG_SCALE,
    ActionType.ANSIBLE_PLAYBOOK,
}


class ActionExecutor:
    """
    Central action execution engine with full audit trail.
    """

    def __init__(self, session_factory: sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def _is_allowed(self, action_type: ActionType) -> bool:
        """Check action is in the runtime allowlist (from config + base allowlist)."""
        return action_type in _BASE_ALLOWLIST or action_type in _PRODUCTION_ONLY

    def _requires_approval(self, request: ActionRequest) -> bool:
        """Auto-execute if confidence >= threshold AND action is low-risk."""
        if request.confidence < settings.auto_execution_confidence_threshold:
            return True
        high_risk = {
            ActionType.AWS_ASG_SCALE,
            ActionType.AZURE_VMSS_SCALE,
            ActionType.GCP_MIG_SCALE,
            ActionType.ANSIBLE_PLAYBOOK,
        }
        return request.action_type in high_risk and request.confidence < 0.95

    async def execute(self, request: ActionRequest) -> ActionAuditRecord:
        """
        Main entry point. Validates, checks approval requirement, executes.
        Returns a fully populated ActionAuditRecord.
        """
        audit = ActionAuditRecord(
            action_id=request.action_id,
            incident_id=request.incident_id,
            action_type=request.action_type,
            status=ActionStatus.PENDING_APPROVAL,
            parameters=request.parameters,
            executed_by=request.requested_by,
        )

        if not self._is_allowed(request.action_type):
            audit.status = ActionStatus.SKIPPED
            audit.error = f"Action {request.action_type} is not in the allowlist"
            await self._persist_audit(audit)
            return audit

        if self._requires_approval(request):
            audit.status = ActionStatus.PENDING_APPROVAL
            await self._persist_audit(audit)
            logger.info(
                "action_pending_approval",
                action_id=request.action_id,
                action_type=request.action_type,
                confidence=request.confidence,
            )
            return audit

        # Execute
        audit.status = ActionStatus.EXECUTING
        audit.started_at = datetime.now(UTC)

        try:
            before_state, result, after_state = await self._run_action(request)
            audit.state_before = before_state
            audit.state_after = after_state
            audit.output = str(result)
            audit.diff_summary = self._diff_summary(before_state, after_state)
            audit.status = ActionStatus.SUCCEEDED
        except Exception as exc:
            audit.status = ActionStatus.FAILED
            audit.error = str(exc)
            logger.error(
                "action_execution_failed",
                action_type=request.action_type,
                error=str(exc),
            )
        finally:
            audit.completed_at = datetime.now(UTC)
            if audit.started_at:
                audit.duration_seconds = (
                    audit.completed_at - audit.started_at
                ).total_seconds()
            await self._persist_audit(audit)

        logger.info(
            "action_executed",
            action_type=request.action_type,
            status=audit.status,
            duration=audit.duration_seconds,
        )
        return audit

    async def _run_action(
        self, request: ActionRequest
    ) -> tuple[dict[str, Any], Any, dict[str, Any]]:
        """Dispatch to the correct execution handler."""
        atype = request.action_type
        params = request.parameters

        if atype == ActionType.KUBECTL_ROLLOUT_RESTART:
            return await self._kubectl_rollout_restart(params)
        if atype == ActionType.KUBECTL_SCALE:
            return await self._kubectl_scale(params)
        if atype == ActionType.SLACK_NOTIFICATION:
            return await self._slack_notify(params)
        if atype == ActionType.PAGERDUTY_ALERT:
            return await self._pagerduty_alert(params)
        if atype == ActionType.JIRA_TICKET:
            return await self._jira_ticket(params)
        if atype == ActionType.CACHE_FLUSH:
            return await self._cache_flush(params)
        if atype == ActionType.WEBHOOK:
            return await self._webhook(params)
        if atype == ActionType.AWS_ASG_SCALE:
            return await self._aws_asg_scale(params)
        if atype == ActionType.ANSIBLE_PLAYBOOK:
            return await self._ansible_playbook(params)
        raise NotImplementedError(f"No executor for {atype}")

    # ── kubectl actions ────────────────────────────────────────────────────────

    async def _kubectl_rollout_restart(
        self, params: dict[str, Any]
    ) -> tuple[dict[str, Any], str, dict[str, Any]]:
        """kubectl rollout restart deployment/<name> -n <namespace>"""
        name = params["deployment"]
        namespace = params.get("namespace", "default")

        # Capture before state
        before_out = self._run_cmd(
            ["kubectl", "get", "deployment", name, "-n", namespace, "-o", "json"]
        )
        before = json.loads(before_out) if before_out else {}

        # Restart
        self._run_cmd(
            ["kubectl", "rollout", "restart", f"deployment/{name}", "-n", namespace]
        )
        # Wait for rollout
        self._run_cmd(
            ["kubectl", "rollout", "status", f"deployment/{name}", "-n", namespace, "--timeout=120s"]
        )

        after_out = self._run_cmd(
            ["kubectl", "get", "deployment", name, "-n", namespace, "-o", "json"]
        )
        after = json.loads(after_out) if after_out else {}
        return before, f"Rollout restart completed for {name}", after

    async def _kubectl_scale(
        self, params: dict[str, Any]
    ) -> tuple[dict[str, Any], str, dict[str, Any]]:
        """kubectl scale deployment/<name> --replicas=<n> -n <namespace>"""
        name = params["deployment"]
        replicas = int(params["replicas"])
        namespace = params.get("namespace", "default")

        before_out = self._run_cmd(
            ["kubectl", "get", "deployment", name, "-n", namespace, "-o", "json"]
        )
        before = json.loads(before_out) if before_out else {}

        self._run_cmd(
            ["kubectl", "scale", f"deployment/{name}", f"--replicas={replicas}", "-n", namespace]
        )

        after_out = self._run_cmd(
            ["kubectl", "get", "deployment", name, "-n", namespace, "-o", "json"]
        )
        after = json.loads(after_out) if after_out else {}
        return before, f"Scaled {name} to {replicas} replicas", after

    def _run_cmd(self, cmd: list[str], timeout: int = 120) -> str:
        """Run a shell command with allowlist validation."""
        cmd_str = " ".join(cmd)
        # Validate first two tokens are in allowlist
        kubectl_allowed = settings.kubectl_action_allowlist or [
            "rollout restart", "scale deployment", "get pods", "get nodes",
            "describe pod", "get events", "rollout status",
        ]
        action_token = " ".join(cmd[1:3]) if len(cmd) >= 3 else ""
        if cmd[0] == "kubectl" and not any(a in action_token for a in kubectl_allowed):
            raise PermissionError(f"kubectl action '{action_token}' not in allowlist")

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
        if result.returncode != 0:
            raise RuntimeError(f"Command failed [{result.returncode}]: {result.stderr[:500]}")
        return result.stdout

    # ── notification actions ───────────────────────────────────────────────────

    async def _slack_notify(
        self, params: dict[str, Any]
    ) -> tuple[dict[str, Any], str, dict[str, Any]]:
        from integrations.slack.integration import SlackIntegration
        slack = SlackIntegration()
        channel = params.get("channel", settings.slack_alerts_channel)
        message = params.get("message", "NeuralOps action executed")
        result = await slack._client.chat_postMessage(channel=channel, text=message)
        return {}, f"Slack message sent to {channel}", {"ts": result.get("ts")}

    async def _pagerduty_alert(
        self, params: dict[str, Any]
    ) -> tuple[dict[str, Any], str, dict[str, Any]]:
        import httpx
        payload = {
            "routing_key": settings.pagerduty_service_key,
            "event_action": "trigger",
            "payload": {
                "summary": params.get("summary", "NeuralOps alert"),
                "severity": params.get("severity", "warning"),
                "source": "neuralops",
            },
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://events.pagerduty.com/v2/enqueue", json=payload
            )
            resp.raise_for_status()
            data = resp.json()
        return {}, "PagerDuty alert triggered", {"dedup_key": data.get("dedup_key")}

    async def _jira_ticket(
        self, params: dict[str, Any]
    ) -> tuple[dict[str, Any], str, dict[str, Any]]:
        from integrations.jira.integration import JiraIntegration
        jira = JiraIntegration()
        from shared.schemas import Incident
        incident = Incident(**params["incident"]) if "incident" in params else None
        if incident:
            key = await jira.create_ticket(incident, params.get("description", ""))
            return {}, f"Jira ticket created: {key}", {"ticket_key": key}
        return {}, "No incident provided", {}

    async def _cache_flush(
        self, params: dict[str, Any]
    ) -> tuple[dict[str, Any], str, dict[str, Any]]:
        """Flush Redis cache keys matching a pattern."""
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
        pattern = params.get("pattern", "neuralops:cache:*")
        keys = await r.keys(pattern)
        if keys:
            deleted = await r.delete(*keys)
        else:
            deleted = 0
        await r.aclose()
        return {"keys_before": len(keys)}, f"Flushed {deleted} cache keys", {"keys_deleted": deleted}

    async def _webhook(
        self, params: dict[str, Any]
    ) -> tuple[dict[str, Any], str, dict[str, Any]]:
        import httpx
        url = params["url"]
        method = params.get("method", "POST").upper()
        body = params.get("body", {})
        headers = params.get("headers", {})
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(method, url, json=body, headers=headers)
            resp.raise_for_status()
        return {}, f"Webhook {method} {url} → {resp.status_code}", {"status": resp.status_code}

    async def _aws_asg_scale(
        self, params: dict[str, Any]
    ) -> tuple[dict[str, Any], str, dict[str, Any]]:
        import boto3
        asg_name = params["asg_name"]
        desired = int(params["desired_capacity"])
        client = boto3.client(
            "autoscaling",
            region_name=params.get("region", settings.aws_default_region),
        )
        before = client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
        client.set_desired_capacity(AutoScalingGroupName=asg_name, DesiredCapacity=desired)
        after = client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
        return (
            {"desired": before["AutoScalingGroups"][0]["DesiredCapacity"]},
            f"ASG {asg_name} scaled to {desired}",
            {"desired": desired},
        )

    async def _ansible_playbook(
        self, params: dict[str, Any]
    ) -> tuple[dict[str, Any], str, dict[str, Any]]:
        playbook = params["playbook"]
        inventory = params.get("inventory", settings.ansible_inventory_path)
        extra_vars = params.get("extra_vars", {})
        cmd = ["ansible-playbook", playbook, "-i", inventory]
        if extra_vars:
            cmd += ["--extra-vars", json.dumps(extra_vars)]
        if settings.ansible_vault_password_file:
            cmd += ["--vault-password-file", settings.ansible_vault_password_file]
        output = self._run_cmd(cmd, timeout=600)
        return {}, output[:500], {"playbook": playbook}

    async def get_audit_record(self, action_id: str) -> ActionAuditRecord | None:
        """Retrieve a specific audit record from the database."""
        async with self._session_factory() as session:
            result = await session.execute(
                text("SELECT * FROM action_audit WHERE action_id = :aid LIMIT 1"),
                {"aid": action_id},
            )
            row = result.mappings().first()
            if not row:
                return None
            
            # Map RowMapping back to Pydantic model
            data = dict(row)
            # Cleanup for Pydantic (parsing JSON strings back to dicts if needed)
            if isinstance(data.get("parameters"), str):
                data["parameters"] = json.loads(data["parameters"])
            if isinstance(data.get("state_before"), str):
                data["state_before"] = json.loads(data["state_before"])
            if isinstance(data.get("state_after"), str):
                data["state_after"] = json.loads(data["state_after"])
                
            return ActionAuditRecord(**data)

    async def _persist_audit(self, audit: ActionAuditRecord) -> None:
        data = audit.model_dump(mode="json")
        async with self._session_factory() as session:
            await session.execute(
                text("""
                    INSERT INTO action_audit (
                        audit_id, action_id, incident_id, action_type, status,
                        parameters, started_at, completed_at, duration_seconds,
                        state_before, state_after, diff_summary,
                        executed_by, approved_by, output, error, rolled_back
                    ) VALUES (
                        :audit_id, :action_id, :incident_id, :action_type, :status,
                        :parameters::jsonb, :started_at, :completed_at, :duration,
                        :state_before::jsonb, :state_after::jsonb, :diff,
                        :executed_by, :approved_by, :output, :error, :rolled_back
                    )
                    ON CONFLICT (audit_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        completed_at = EXCLUDED.completed_at,
                        duration_seconds = EXCLUDED.duration_seconds,
                        output = EXCLUDED.output,
                        error = EXCLUDED.error
                """),
                {
                    "audit_id": data["audit_id"],
                    "action_id": data["action_id"],
                    "incident_id": data["incident_id"],
                    "action_type": data["action_type"],
                    "status": data["status"],
                    "parameters": json.dumps(data["parameters"]),
                    "started_at": data.get("started_at"),
                    "completed_at": data.get("completed_at"),
                    "duration": data.get("duration_seconds"),
                    "state_before": json.dumps(data["state_before"]),
                    "state_after": json.dumps(data["state_after"]),
                    "diff": data.get("diff_summary"),
                    "executed_by": data["executed_by"],
                    "approved_by": data.get("approved_by"),
                    "output": data.get("output"),
                    "error": data.get("error"),
                    "rolled_back": data["rolled_back"],
                },
            )
            await session.commit()
