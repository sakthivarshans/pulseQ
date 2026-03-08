"""
integrations/github/integration.py
────────────────────────────────────
GitHub integration — queries recent deployments and commits for RCA context.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog

from shared.config import get_settings
from shared.interfaces import ToolIntegrationInterface
from shared.schemas import DeploymentRecord, Incident

logger = structlog.get_logger(__name__)
settings = get_settings()


class GitHubIntegration(ToolIntegrationInterface):

    def __init__(self) -> None:
        self._token = settings.github_token or ""
        self._base_url = "https://api.github.com"
        self._headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def get_recent_deployments(
        self,
        service_names: list[str] | None = None,
        lookback_hours: int = 24,
        repo: str | None = None,
    ) -> list[DeploymentRecord]:
        """Fetch recent GitHub Deployments API records."""
        deployments: list[DeploymentRecord] = []
        repos_to_check = [repo] if repo else (settings.github_monitored_repos or [])
        since = datetime.now(UTC) - timedelta(hours=lookback_hours)

        async with httpx.AsyncClient(headers=self._headers, timeout=15.0) as client:
            for repo_name in repos_to_check[:10]:
                try:
                    resp = await client.get(
                        f"{self._base_url}/repos/{repo_name}/deployments",
                        params={"per_page": 30},
                    )
                    resp.raise_for_status()
                    for dep in resp.json():
                        created_at = datetime.fromisoformat(
                            dep["created_at"].replace("Z", "+00:00")
                        )
                        if created_at < since:
                            continue
                        # Get the deployer from the sha commit
                        sha = dep.get("sha", "")
                        commit_message = ""
                        deployed_by = dep.get("creator", {}).get("login", "unknown")
                        if sha:
                            try:
                                c_resp = await client.get(
                                    f"{self._base_url}/repos/{repo_name}/commits/{sha[:7]}"
                                )
                                if c_resp.status_code == 200:
                                    c_data = c_resp.json()
                                    commit_message = c_data.get("commit", {}).get("message", "")[:200]
                            except Exception:
                                pass
                        service_name = dep.get("task", repo_name.split("/")[-1])
                        if service_names and service_name not in service_names:
                            continue
                        deployments.append(DeploymentRecord(
                            service_name=service_name,
                            version=sha[:7] if sha else "unknown",
                            deployed_at=created_at,
                            deployed_by=deployed_by,
                            environment=dep.get("environment", "production"),
                            commit_sha=sha,
                            commit_message=commit_message,
                            repo=repo_name,
                            source="github",
                        ))
                except httpx.HTTPError as exc:
                    logger.warning("github_deploy_fetch_failed", repo=repo_name, error=str(exc))
        return sorted(deployments, key=lambda d: d.deployed_at, reverse=True)

    async def send_alert(self, incident: Incident) -> str | None:
        """Create a GitHub Issue for the incident in a designated repo."""
        if not settings.github_issues_repo:
            return None
        body = (
            f"## [{incident.severity}] {incident.title}\n\n"
            f"- **Service**: {incident.primary_service}\n"
            f"- **Affected**: {', '.join(incident.affected_services)}\n"
            f"- **Environment**: {incident.environment}\n"
            f"- **Detected**: {incident.detected_at.isoformat()}\n"
            f"- **ML Score**: {incident.peak_anomaly_score}\n\n"
            f"[View in NeuralOps]({settings.api_base_url}/incidents/{incident.incident_id})\n\n"
            f"_Opened automatically by NeuralOps AI_"
        )
        async with httpx.AsyncClient(headers=self._headers, timeout=10.0) as client:
            resp = await client.post(
                f"{self._base_url}/repos/{settings.github_issues_repo}/issues",
                json={
                    "title": f"[{incident.severity}] {incident.title}",
                    "body": body,
                    "labels": ["incident", incident.severity.lower(), "neuralops"],
                },
            )
            resp.raise_for_status()
            return str(resp.json()["number"])

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(headers=self._headers, timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/user")
                return resp.status_code == 200
        except Exception:
            return False

    async def execute_action(self, action_type: str, parameters: dict[str, Any]) -> dict[str, Any]:
        return {"error": f"Action {action_type} not implemented for GitHub"}

    async def get_status(self) -> dict[str, Any]:
        healthy = await self.health_check()
        return {"integration": "github", "healthy": healthy}
