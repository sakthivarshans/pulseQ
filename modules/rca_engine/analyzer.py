"""
modules/rca_engine/analyzer.py
─────────────────────────────
RCA Engine LLM caller and result parser.

Uses structured, DevOps-expert system prompts to instruct Gemini 1.5 Flash
(or Phi-3 Mini fallback) to perform root cause analysis.
Parses the structured JSON response into a validated RCAResult object.
Stores the result in PostgreSQL and ChromaDB.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.rca_engine.context_builder import RCAContextBuilder
from shared.interfaces import LLMProviderError
from shared.llm import get_llm_provider
from shared.schemas import (
    Incident,
    RCAResult,
    RemediationStep,
    SimilarIncident,
)

logger = structlog.get_logger(__name__)

# ── System prompt — engineered for expert SRE role ───────────────────────────
_SRE_SYSTEM_PROMPT = """You are an Expert Site Reliability Engineer (SRE) with 15 years of experience \
managing large-scale distributed systems across AWS, Azure, and GCP. You have deep expertise in \
Kubernetes, microservices, observability, incident response, and root cause analysis.

You are performing root cause analysis for a production incident. You will be given:
- Incident metadata (severity, affected services, ML anomaly scores)
- Correlated logs from the incident window
- Metric statistical summaries (min/max/avg/last values)
- Recent deployments in the last 24 hours
- Infrastructure state snapshot
- Similar past incidents with their resolutions

Your analysis MUST follow this structured approach:
1. Identify the primary root cause based on evidence from logs and metrics
2. Identify contributing factors (secondary causes)
3. Assess confidence based on quality and quantity of evidence
4. Produce a concrete, step-by-step remediation plan with specific commands where applicable
5. Estimate time to resolve based on complexity
6. Assess recurrence risk

CRITICAL RULES:
- Base ALL conclusions on actual evidence in the provided context
- Be specific with service names, metric values, and log patterns
- If a recent deployment correlates with the incident timing, it is a strong suspect
- For Kubernetes incidents, suggest specific kubectl commands
- For resource exhaustion, suggest specific scaling actions
- Produce conservative, safe remediation steps ordered from least to most disruptive

You MUST respond with a single valid JSON object matching this exact schema:
{
  "root_cause_summary": "string — 1-3 sentence plain-language explanation",
  "root_cause_confidence": 0.0-1.0,
  "primary_contributing_factor": "string",
  "secondary_contributing_factors": ["string", ...],
  "affected_components": ["service-name", ...],
  "remediation_steps": [
    {
      "step_number": 1,
      "action": "string — specific action to take",
      "rationale": "string — why this step",
      "estimated_duration_minutes": integer,
      "risk_level": "low|medium|high",
      "automation_eligible": true/false,
      "action_type": "kubectl_rollout_restart|kubectl_scale|aws_asg_scale|slack_notification|null",
      "action_parameters": {}
    }
  ],
  "estimated_resolution_minutes": integer,
  "recurrence_risk": "low|medium|high",
  "recurrence_reasoning": "string",
  "runbook_markdown": "string — auto-generated runbook in Markdown for this incident type"
}"""


class RCAAnalyzer:
    """
    Orchestrates the full RCA flow:
    1. Build context (delegated to RCAContextBuilder)
    2. Send to LLM with engineered prompt
    3. Parse and validate JSON response
    4. Store in PostgreSQL + ChromaDB
    """

    def __init__(self, context_builder: RCAContextBuilder, session: AsyncSession) -> None:
        self._context_builder = context_builder
        self._session = session

    async def analyze(self, incident: Incident) -> RCAResult:
        """
        Run full RCA for the given incident.
        Returns a validated RCAResult with all fields populated.
        """
        # 1. Build context
        context = await self._context_builder.build(incident)
        user_prompt = self._format_user_prompt(context)

        # 2. Call LLM with automatic fallback
        llm = get_llm_provider()
        provider_used = llm.provider_name
        try:
            result_dict = await llm.generate_json(
                system_prompt=_SRE_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.1,
                max_tokens=4096,
            )
        except LLMProviderError as exc:
            logger.error("rca_llm_failed", provider=exc.provider, error=str(exc))
            # Hard fallback: generate minimal RCA from heuristics
            result_dict = self._heuristic_fallback(incident, context)
            provider_used = "heuristic"

        # 3. Parse and validate
        rca_result = self._parse_result(incident, result_dict, provider_used, context)

        # 4. Persist to PostgreSQL
        await self._persist_rca(rca_result)

        # 5. Store embedding in ChromaDB (async, best-effort)
        try:
            await self._store_embedding(incident, rca_result)
        except Exception as exc:
            logger.warning("rca_embedding_failed", error=str(exc))

        logger.info(
            "rca_complete",
            incident_id=incident.incident_id,
            provider=provider_used,
            confidence=rca_result.root_cause_confidence,
        )
        return rca_result

    def _format_user_prompt(self, context: dict[str, Any]) -> str:
        """Format context dict into a structured prompt string."""
        incident = context["incident"]
        logs = context.get("correlated_logs", [])[:50]
        metrics = context.get("metric_summaries", {})
        deployments = context.get("recent_deployments", [])
        similar = context.get("similar_past_incidents", [])

        prompt_parts = [
            f"## Incident: {incident['title']}",
            f"- Severity: {incident['severity']}",
            f"- Primary service: {incident['primary_service']}",
            f"- All affected services: {', '.join(incident['affected_services'])}",
            f"- ML Anomaly Score: {incident['peak_anomaly_score']} (confidence: {incident['ml_confidence']})",
            f"- Detected at: {incident['detected_at']}",
            "",
            "## Metric Summaries (during incident window)",
        ]
        for svc, svc_metrics in metrics.items():
            prompt_parts.append(f"\n### {svc}")
            for mtype, stats in svc_metrics.items():
                prompt_parts.append(
                    f"  {mtype}: avg={stats['avg']}, max={stats['max']}, last={stats['last']}"
                )

        prompt_parts.append("\n## Correlated Logs (errors first)")
        prompt_parts.extend(logs[:50])

        if deployments:
            prompt_parts.append("\n## Recent Deployments (last 24h)")
            for d in deployments[:10]:
                prompt_parts.append(
                    f"  [{d.get('deployed_at', 'N/A')}] {d.get('service_name')} "
                    f"v{d.get('version')} by {d.get('deployed_by', 'unknown')} "
                    f"— commit: {d.get('commit_message', '')[:80]}"
                )

        if similar:
            prompt_parts.append("\n## Similar Past Incidents")
            for s in similar[:5]:
                prompt_parts.append(
                    f"  [{s.get('similarity_score', 0):.0%} match] {s.get('title')}: "
                    f"{s.get('root_cause_summary', '')} → resolved in {s.get('mttr_minutes', '?')}min"
                )

        prompt_parts.append(
            "\n\nAnalyze the above incident context and produce your RCA JSON response."
        )
        return "\n".join(prompt_parts)

    def _parse_result(
        self,
        incident: Incident,
        raw: dict[str, Any],
        provider: str,
        context: dict[str, Any],
    ) -> RCAResult:
        """Parse and validate LLM JSON response into RCAResult."""
        steps = [
            RemediationStep(**step) for step in raw.get("remediation_steps", [])
        ]
        similar = [
            SimilarIncident(**s) for s in context.get("similar_past_incidents", [])
            if isinstance(s, dict) and "incident_id" in s and "title" in s and "similarity_score" in s and "detected_at" in s
        ]
        return RCAResult(
            incident_id=incident.incident_id,
            llm_provider_used=provider,
            root_cause_summary=raw.get("root_cause_summary", "Analysis incomplete — LLM error"),
            root_cause_confidence=float(raw.get("root_cause_confidence", 0.5)),
            primary_contributing_factor=raw.get("primary_contributing_factor", "Unknown"),
            secondary_contributing_factors=raw.get("secondary_contributing_factors", []),
            affected_components=raw.get("affected_components", incident.affected_services),
            remediation_steps=steps,
            estimated_resolution_minutes=raw.get("estimated_resolution_minutes"),
            recurrence_risk=raw.get("recurrence_risk", "medium"),
            recurrence_reasoning=raw.get("recurrence_reasoning"),
            similar_incidents=similar,
            logs_analyzed_count=len(context.get("correlated_logs", [])),
            deployments_checked_count=len(context.get("recent_deployments", [])),
            runbook_markdown=raw.get("runbook_markdown"),
        )

    def _heuristic_fallback(self, incident: Incident, context: dict[str, Any]) -> dict[str, Any]:
        """Generate a minimal RCA based on simple heuristics when LLM is unavailable."""
        metrics = context.get("metric_summaries", {})
        svc = incident.primary_service
        svc_metrics = metrics.get(svc, {})
        factors = []
        if "cpu" in svc_metrics and svc_metrics["cpu"].get("max", 0) > 80:
            factors.append("High CPU utilization detected")
        if "memory" in svc_metrics and svc_metrics["memory"].get("max", 0) > 85:
            factors.append("High memory utilization — possible memory leak or insufficient allocation")
        if "error_rate" in svc_metrics and svc_metrics["error_rate"].get("avg", 0) > 5:
            factors.append(f"Elevated error rate: {svc_metrics['error_rate']['avg']:.1f}%")
        if context.get("recent_deployments"):
            factors.append("Recent deployment detected in correlation window — possible regression")
        if not factors:
            factors.append("Anomalous metric behavior detected by ML models")
        return {
            "root_cause_summary": f"Heuristic analysis (LLM unavailable): {'; '.join(factors[:2])}",
            "root_cause_confidence": 0.35,
            "primary_contributing_factor": factors[0] if factors else "Unknown",
            "secondary_contributing_factors": factors[1:],
            "affected_components": incident.affected_services,
            "remediation_steps": [
                {
                    "step_number": 1,
                    "action": f"Investigate {svc} logs and recent changes",
                    "rationale": "Gather more context to identify root cause",
                    "estimated_duration_minutes": 15,
                    "risk_level": "low",
                    "automation_eligible": False,
                    "action_type": None,
                    "action_parameters": {},
                }
            ],
            "estimated_resolution_minutes": 60,
            "recurrence_risk": "medium",
            "recurrence_reasoning": "Unable to assess — LLM unavailable",
            "runbook_markdown": f"# Incident Runbook: {incident.title}\n\n## Steps\n1. Check {svc} logs\n2. Review recent deployments\n3. Escalate if unresolved within 30 minutes\n",
        }

    async def _persist_rca(self, result: RCAResult) -> None:
        data = result.model_dump(mode="json")
        await self._session.execute(
            text("""
                INSERT INTO rca_results (
                    rca_id, incident_id, created_at, llm_provider_used,
                    root_cause_summary, root_cause_confidence, primary_contributing_factor,
                    secondary_contributing_factors, affected_components, remediation_steps,
                    estimated_resolution_minutes, recurrence_risk, recurrence_reasoning,
                    similar_incidents, logs_analyzed_count, deployments_checked_count,
                    runbook_markdown
                ) VALUES (
                    :rca_id, :incident_id, :created_at, :provider,
                    :rc_summary, :rc_confidence, :primary_factor,
                    :secondary::jsonb, :affected::jsonb, :steps::jsonb,
                    :est_minutes, :rec_risk, :rec_reason,
                    :similar::jsonb, :logs_count, :deploys_count,
                    :runbook
                )
                ON CONFLICT (rca_id) DO NOTHING
            """),
            {
                "rca_id": data["rca_id"],
                "incident_id": data["incident_id"],
                "created_at": data["created_at"],
                "provider": data["llm_provider_used"],
                "rc_summary": data["root_cause_summary"],
                "rc_confidence": data["root_cause_confidence"],
                "primary_factor": data["primary_contributing_factor"],
                "secondary": json.dumps(data["secondary_contributing_factors"]),
                "affected": json.dumps(data["affected_components"]),
                "steps": json.dumps(data["remediation_steps"]),
                "est_minutes": data.get("estimated_resolution_minutes"),
                "rec_risk": data["recurrence_risk"],
                "rec_reason": data.get("recurrence_reasoning"),
                "similar": json.dumps(data["similar_incidents"]),
                "logs_count": data["logs_analyzed_count"],
                "deploys_count": data["deployments_checked_count"],
                "runbook": data.get("runbook_markdown"),
            },
        )
        await self._session.commit()

        # Update incident record with rca_id
        await self._session.execute(
            text("UPDATE incidents SET rca_id = :rca_id WHERE incident_id = :iid"),
            {"rca_id": data["rca_id"], "iid": data["incident_id"]},
        )
        await self._session.commit()

    async def _store_embedding(self, incident: Incident, result: RCAResult) -> None:
        """Store RCA embedding in ChromaDB via Memory module HTTP API."""
        import httpx
        document = (
            f"Incident: {incident.title}\n"
            f"Service: {incident.primary_service}\n"
            f"Root cause: {result.root_cause_summary}\n"
            f"Primary factor: {result.primary_contributing_factor}\n"
            f"Remediation: {'; '.join(s.action for s in result.remediation_steps[:3])}"
        )
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                "http://memory:8060/store",
                json={
                    "incident_id": incident.incident_id,
                    "document": document,
                    "metadata": {
                        "severity": incident.severity,
                        "primary_service": incident.primary_service,
                        "rca_id": result.rca_id,
                    },
                },
            )
