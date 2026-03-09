"""
modules/api/routers/predictions.py
────────────────────────────────────
Predictions endpoints — reads from predictions table, JOINs repositories
so every prediction includes repo_name, repo_owner, and repo_language.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import structlog
from fastapi import APIRouter, HTTPException
from sqlalchemy import text

router = APIRouter(prefix="/api/v1/predictions", tags=["predictions"])
logger = structlog.get_logger(__name__)


def _get_severity(confidence: float) -> str:
    if confidence >= 0.90:
        return "P1"
    elif confidence >= 0.75:
        return "P2"
    elif confidence >= 0.60:
        return "P3"
    return "P4"


def _time_until(dt: Any) -> str:
    if not dt:
        return "Unknown"
    now = datetime.now(timezone.utc)
    if hasattr(dt, "tzinfo"):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    else:
        return "Unknown"
    diff = dt - now
    if diff.total_seconds() < 0:
        return "Overdue"
    hours = int(diff.total_seconds() // 3600)
    minutes = int((diff.total_seconds() % 3600) // 60)
    if hours > 0:
        return f"~{hours}h away"
    return f"~{minutes}m away"


@router.get("")
async def get_predictions(
    project_id: Optional[str] = None,
    severity: Optional[str] = None,
) -> dict[str, Any]:
    """
    Return active predictions joined with repository info.
    Falls back to empty list if DB is unavailable.
    """
    # Dynamically import _sf to avoid circular imports
    try:
        import modules.api.main as _main
        db_session = getattr(_main, '_sf', None)
    except Exception:
        db_session = None

    if db_session is None:
        return {"predictions": [], "total": 0, "by_severity": {"P1": 0, "P2": 0, "P3": 0, "P4": 0}}

    try:
        async with db_session() as session:
            where_clauses = ["p.status = 'active'"]
            params: dict[str, Any] = {}

            if project_id:
                where_clauses.append("p.repo_id = :repo_id")
                params["repo_id"] = project_id

            where_sql = " AND ".join(where_clauses)

            result = await session.execute(
                text(f"""
                    SELECT
                        p.id,
                        p.repo_id,
                        p.service_name,
                        p.prediction_type,
                        p.description,
                        p.confidence,
                        p.status,
                        p.estimated_impact_time,
                        p.created_at,
                        r.name        AS repo_name,
                        r.owner       AS repo_owner,
                        r.primary_language AS repo_language,
                        r.is_default  AS repo_is_default
                    FROM predictions p
                    LEFT JOIN repositories r ON r.id = p.repo_id
                    WHERE {where_sql}
                    ORDER BY p.confidence DESC
                """),
                params,
            )
            rows = result.mappings().all()

        predictions = []
        for row in rows:
            sev = _get_severity(float(row["confidence"]))
            if severity and sev != severity:
                continue
            predictions.append({
                "id": str(row["id"]),
                "repo_id": str(row["repo_id"]) if row["repo_id"] else None,
                "repo_name": row["repo_name"] or row["service_name"] or "unknown",
                "repo_owner": row["repo_owner"] or "unknown",
                "repo_language": row["repo_language"] or "Python",
                "repo_is_default": bool(row["repo_is_default"]) if row["repo_is_default"] is not None else False,
                "service_name": row["service_name"] or "unknown",
                "prediction_type": row["prediction_type"],
                "description": row["description"] or "",
                "confidence": float(row["confidence"]),
                "severity": sev,
                "estimated_impact_time": row["estimated_impact_time"].isoformat() if row["estimated_impact_time"] else None,
                "time_until_impact": _time_until(row["estimated_impact_time"]),
                "status": row["status"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else "",
            })

        by_severity: dict[str, int] = {"P1": 0, "P2": 0, "P3": 0, "P4": 0}
        for p in predictions:
            s = p["severity"]
            if s in by_severity:
                by_severity[s] += 1

        return {
            "predictions": predictions,
            "total": len(predictions),
            "by_severity": by_severity,
        }

    except Exception as exc:
        logger.warning("get_predictions_failed", error=str(exc))
        return {"predictions": [], "total": 0, "by_severity": {"P1": 0, "P2": 0, "P3": 0, "P4": 0}}


@router.post("/{prediction_id}/snooze")
async def snooze_prediction(
    prediction_id: str,
) -> dict[str, Any]:
    """
    Snooze a prediction for 24 hours.
    Sets status='snoozed' and snoozed_until=now+24h.
    """
    # Dynamically import _sf to avoid circular imports
    try:
        import modules.api.main as _main
        db_session = getattr(_main, '_sf', None)
    except Exception:
        db_session = None

    if db_session is None:
        raise HTTPException(status_code=503, detail="Database not available")

    snooze_until = datetime.now(timezone.utc) + timedelta(hours=24)

    try:
        async with db_session() as session:
            result = await session.execute(
                text("""
                    UPDATE predictions
                    SET status = 'snoozed',
                        snoozed_until = :snoozed_until,
                        updated_at = NOW()
                    WHERE id = :pid
                    RETURNING id
                """),
                {"pid": prediction_id, "snoozed_until": snooze_until},
            )
            row = result.fetchone()
            await session.commit()

        if not row:
            raise HTTPException(status_code=404, detail="Prediction not found")

        return {"status": "snoozed", "snoozed_until": snooze_until.isoformat()}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("snooze_prediction_failed", prediction_id=prediction_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to snooze prediction: {exc}")
