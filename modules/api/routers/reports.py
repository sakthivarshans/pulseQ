"""
modules/api/routers/reports.py
───────────────────────────────
Weekly summary report endpoint.
Queries incidents from the past 7 days and returns structured JSON
that the frontend converts to a downloadable HTML report.
"""
from __future__ import annotations

from datetime import datetime, timedelta, UTC
from typing import Any

import structlog
from fastapi import APIRouter
from sqlalchemy import text

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])
logger = structlog.get_logger(__name__)


@router.get("/weekly")
async def get_weekly_summary(db_session=None) -> dict[str, Any]:
    """Return structured weekly summary for the past 7 days."""
    end = datetime.now(UTC)
    start = end - timedelta(days=7)

    empty = {
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "total_incidents": 0,
        "by_severity": {},
        "resolved_count": 0,
        "avg_mttr_minutes": 0,
        "top_services": [],
        "incidents": [],
    }

    if db_session is None:
        return empty

    try:
        async with db_session() as session:
            result = await session.execute(
                text(
                    "SELECT incident_id, title, severity, status, detected_at, "
                    "       resolved_at, mttr_minutes, primary_service, "
                    "       affected_services, root_cause, remediation_steps "
                    "FROM incidents "
                    "WHERE detected_at >= :start "
                    "ORDER BY detected_at DESC"
                ),
                {"start": start},
            )
            rows = result.mappings().all()

        if not rows:
            return empty

        resolved = [r for r in rows if r["status"] == "resolved" and r["mttr_minutes"]]
        avg_mttr = (
            sum(r["mttr_minutes"] for r in resolved) / len(resolved)
            if resolved else 0
        )

        by_severity: dict[str, int] = {}
        service_counts: dict[str, int] = {}
        for r in rows:
            sev = r["severity"] or "Unknown"
            by_severity[sev] = by_severity.get(sev, 0) + 1
            svc = r["primary_service"] or "unknown"
            service_counts[svc] = service_counts.get(svc, 0) + 1

        top_services = sorted(service_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        incidents_list = []
        for r in rows:
            incidents_list.append({
                "id": str(r["incident_id"]),
                "title": r["title"],
                "severity": r["severity"],
                "status": r["status"],
                "started_at": r["detected_at"].isoformat() if r["detected_at"] else None,
                "resolved_at": r["resolved_at"].isoformat() if r["resolved_at"] else None,
                "mttr_minutes": r["mttr_minutes"],
                "primary_service": r["primary_service"],
                "root_cause": r["root_cause"],
                "remediation_steps": r["remediation_steps"] if isinstance(r["remediation_steps"], list) else [],
            })

        return {
            "week_start": start.isoformat(),
            "week_end": end.isoformat(),
            "total_incidents": len(rows),
            "by_severity": by_severity,
            "resolved_count": len(resolved),
            "avg_mttr_minutes": round(avg_mttr, 1),
            "top_services": [{"service": s, "count": c} for s, c in top_services],
            "incidents": incidents_list,
        }

    except Exception as exc:
        logger.warning("weekly_summary_failed", error=str(exc))
        return empty
