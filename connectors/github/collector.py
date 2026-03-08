"""
connectors/github/collector.py
───────────────────────────────
GitHub connector implementing CollectorInterface.

Monitors each repo in settings.github_monitored_repos for:
  - Recent commits (author, files changed, risk scoring)
  - GitHub Actions workflow runs (failures, slow builds)
  - Open pull requests (stale PRs, review blockers)

Emits IntelligenceEvent objects that flow through the ML pipeline
into the NeuralOps dashboard as anomalies and incidents.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog

from shared.config import get_settings
from shared.schemas import (
    CloudProvider,
    EventType,
    IntelligenceEvent,
    LogPayload,
    MetricPayload,
    AnomalyMetricType,
)

logger = structlog.get_logger(__name__)
settings = get_settings()

_GITHUB_API = "https://api.github.com"
_POLL_WINDOW_MINUTES = 65  # slightly > poll interval to avoid gaps


class GitHubCollector:
    """
    Polls GitHub repos and emits IntelligenceEvent objects.
    Registered by the ingestion service via _register_connectors().
    One instance covers all repos in settings.github_monitored_repos.
    """

    provider_name = "github"

    def __init__(self) -> None:
        self._headers = {
            "Authorization": f"Bearer {settings.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self._repos = settings.github_monitored_repos
        logger.info("github_connector_initialized", repos=self._repos)

    # ── Public interface (called by IngestionService._collect_from_connectors) ─

    async def collect(self) -> list[IntelligenceEvent]:
        """Collect all GitHub signals: CI runs, commits, PRs."""
        events: list[IntelligenceEvent] = []
        async with httpx.AsyncClient(headers=self._headers, timeout=15) as client:
            tasks = [self._collect_repo(client, repo) for repo in self._repos]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, list):
                    events.extend(result)
                elif isinstance(result, Exception):
                    logger.warning("github_collection_error", error=str(result))
        logger.info("github_collected", event_count=len(events))
        return events

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(headers=self._headers, timeout=5) as client:
                resp = await client.get(f"{_GITHUB_API}/rate_limit")
                return resp.status_code == 200
        except Exception:
            return False

    async def get_resource_inventory(self) -> list[dict[str, Any]]:
        """Return repo metadata for the RCA context builder."""
        inventory = []
        async with httpx.AsyncClient(headers=self._headers, timeout=10) as client:
            for repo in self._repos:
                try:
                    resp = await client.get(f"{_GITHUB_API}/repos/{repo}")
                    if resp.status_code == 200:
                        data = resp.json()
                        inventory.append({
                            "type": "github_repo",
                            "id": str(data.get("id")),
                            "name": data.get("full_name"),
                            "language": data.get("language"),
                            "default_branch": data.get("default_branch", "main"),
                            "open_issues": data.get("open_issues_count", 0),
                            "stars": data.get("stargazers_count", 0),
                        })
                except Exception as exc:
                    logger.warning("github_inventory_failed", repo=repo, error=str(exc))
        return inventory

    # ── Per-repo collection ───────────────────────────────────────────────────

    async def _collect_repo(
        self, client: httpx.AsyncClient, repo: str
    ) -> list[IntelligenceEvent]:
        tasks = [
            self._collect_ci_runs(client, repo),
            self._collect_commits(client, repo),
            self._collect_pr_count(client, repo),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        events: list[IntelligenceEvent] = []
        for r in results:
            if isinstance(r, list):
                events.extend(r)
            elif isinstance(r, Exception):
                logger.warning("github_repo_partial_failure", repo=repo, error=str(r))
        return events

    async def _collect_ci_runs(
        self, client: httpx.AsyncClient, repo: str
    ) -> list[IntelligenceEvent]:
        """Collect GitHub Actions workflow runs → CI success rate metric + failure logs."""
        events: list[IntelligenceEvent] = []
        svc = repo.replace("/", "-")
        try:
            resp = await client.get(
                f"{_GITHUB_API}/repos/{repo}/actions/runs",
                params={"per_page": 20},
            )
            if resp.status_code != 200:
                logger.warning("github_workflow_runs_failed", repo=repo, status=resp.status_code)
                return events

            runs = resp.json().get("workflow_runs", [])
            total = len(runs)
            failures = sum(
                1 for r in runs if r.get("conclusion") in ("failure", "timed_out")
            )
            success_rate = ((total - failures) / total * 100.0) if total else 100.0

            # CI success rate metric
            events.append(IntelligenceEvent(
                event_type=EventType.METRIC,
                source=f"github:{repo}:actions",
                service_name=svc,
                environment=settings.default_environment,
                cloud_provider=CloudProvider.GITHUB,
                metric=MetricPayload(
                    metric_name="ci_success_rate",
                    metric_type=AnomalyMetricType.CI_SUCCESS_RATE,
                    value=success_rate,
                    unit="percent",
                    labels={
                        "repo": repo,
                        "total_runs": str(total),
                        "failed_runs": str(failures),
                    },
                ),
            ))

            # Individual failure log events
            for run in runs:
                if run.get("conclusion") in ("failure", "timed_out"):
                    ts_str = run.get("updated_at", "")
                    ts = (
                        datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        if ts_str else datetime.now(UTC)
                    )
                    events.append(IntelligenceEvent(
                        event_type=EventType.LOG,
                        source=f"github:{repo}:ci",
                        service_name=svc,
                        environment=settings.default_environment,
                        cloud_provider=CloudProvider.GITHUB,
                        timestamp=ts,
                        log=LogPayload(
                            level="ERROR",
                            message=(
                                f"CI FAILED: [{run.get('name', 'workflow')}] "
                                f"branch={run.get('head_branch', 'unknown')} "
                                f"commit={run.get('head_sha', '')[:8]} "
                                f"url={run.get('html_url', '')}"
                            ),
                        ),
                    ))

        except Exception as exc:
            logger.warning("github_ci_collection_failed", repo=repo, error=str(exc))
        return events

    async def _collect_commits(
        self, client: httpx.AsyncClient, repo: str
    ) -> list[IntelligenceEvent]:
        """Collect recent commits → log events with risk-based severity."""
        events: list[IntelligenceEvent] = []
        svc = repo.replace("/", "-")
        try:
            since = (
                datetime.now(UTC) - timedelta(minutes=_POLL_WINDOW_MINUTES)
            ).isoformat()
            resp = await client.get(
                f"{_GITHUB_API}/repos/{repo}/commits",
                params={"since": since, "per_page": 20},
            )
            if resp.status_code != 200:
                return events

            for commit in resp.json():
                sha = commit.get("sha", "")[:8]
                msg = commit.get("commit", {}).get("message", "")[:300]
                author = commit.get("commit", {}).get("author", {}).get("name", "unknown")
                date_str = commit.get("commit", {}).get("author", {}).get("date", "")
                ts = (
                    datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    if date_str else datetime.now(UTC)
                )

                # Risk classification based on commit message keywords
                msg_lower = msg.lower()
                if any(w in msg_lower for w in ("breaking", "break", "remove", "delete", "drop table")):
                    level = "ERROR"
                elif any(w in msg_lower for w in ("fix", "hotfix", "urgent", "revert", "critical")):
                    level = "WARN"
                else:
                    level = "INFO"

                events.append(IntelligenceEvent(
                    event_type=EventType.LOG,
                    source=f"github:{repo}:commit",
                    service_name=svc,
                    environment=settings.default_environment,
                    cloud_provider=CloudProvider.GITHUB,
                    timestamp=ts,
                    dedupe_key=f"github-commit-{sha}",
                    log=LogPayload(
                        level=level,
                        message=f"COMMIT [{sha}] by {author}: {msg}",
                        attributes={
                            "sha": sha,
                            "author": author,
                            "repo": repo,
                            "url": commit.get("html_url", ""),
                        },
                    ),
                ))
        except Exception as exc:
            logger.warning("github_commits_failed", repo=repo, error=str(exc))
        return events

    async def _collect_pr_count(
        self, client: httpx.AsyncClient, repo: str
    ) -> list[IntelligenceEvent]:
        """Emit open PR count as a metric — spikes may indicate review bottlenecks."""
        svc = repo.replace("/", "-")
        try:
            resp = await client.get(
                f"{_GITHUB_API}/repos/{repo}/pulls",
                params={"state": "open", "per_page": 100},
            )
            if resp.status_code != 200:
                return []

            open_prs = len(resp.json())
            return [IntelligenceEvent(
                event_type=EventType.METRIC,
                source=f"github:{repo}:pulls",
                service_name=svc,
                environment=settings.default_environment,
                cloud_provider=CloudProvider.GITHUB,
                metric=MetricPayload(
                    metric_name="open_pr_count",
                    metric_type=AnomalyMetricType.OPEN_PR_COUNT,
                    value=float(open_prs),
                    unit="count",
                    labels={"repo": repo},
                ),
            )]
        except Exception as exc:
            logger.warning("github_prs_failed", repo=repo, error=str(exc))
            return []
