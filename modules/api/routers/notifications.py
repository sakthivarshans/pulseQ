"""
modules/api/routers/notifications.py
─────────────────────────────────────
Notification endpoints: list, mark read, mark all read.
Notifications are stored in PostgreSQL `notifications` table.
"""
from __future__ import annotations

from typing import Any
from datetime import datetime, UTC

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])
logger = structlog.get_logger(__name__)


async def create_notification(
    session: AsyncSession,
    ntype: str,
    title: str,
    message: str,
    link: str | None = None,
) -> None:
    """Insert a notification row. Called by incident creation, anomaly detection, etc."""
    try:
        await session.execute(
            text(
                "INSERT INTO notifications (type, title, message, link) "
                "VALUES (:type, :title, :message, :link)"
            ),
            {"type": ntype, "title": title, "message": message, "link": link},
        )
        await session.commit()
    except Exception as exc:
        logger.warning("notification_insert_failed", error=str(exc))


@router.get("")
async def list_notifications(
    unread: bool = Query(False, description="If true, return only unread notifications"),
    limit: int = Query(50, le=200),
    db_session=None,  # injected by main.py via dependency override
) -> dict[str, Any]:
    """Return recent notifications, optionally filtered to unread only."""
    if db_session is None:
        return {"notifications": [], "unread_count": 0}
    try:
        async with db_session() as session:
            where = "WHERE is_read = FALSE" if unread else ""
            result = await session.execute(
                text(
                    f"SELECT id, type, title, message, link, is_read, created_at "
                    f"FROM notifications {where} "
                    f"ORDER BY created_at DESC LIMIT :limit"
                ),
                {"limit": limit},
            )
            rows = result.mappings().all()

            count_result = await session.execute(
                text("SELECT COUNT(*) FROM notifications WHERE is_read = FALSE")
            )
            unread_count = count_result.scalar() or 0

        return {
            "notifications": [
                {
                    "id": str(r["id"]),
                    "type": r["type"],
                    "title": r["title"],
                    "message": r["message"],
                    "link": r["link"],
                    "is_read": r["is_read"],
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                }
                for r in rows
            ],
            "unread_count": unread_count,
        }
    except Exception as exc:
        logger.warning("notifications_list_failed", error=str(exc))
        return {"notifications": [], "unread_count": 0}


@router.post("/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    db_session=None,
) -> dict[str, str]:
    """Mark a single notification as read."""
    if db_session is None:
        return {"status": "ok"}
    try:
        async with db_session() as session:
            await session.execute(
                text("UPDATE notifications SET is_read = TRUE WHERE id = :id"),
                {"id": notification_id},
            )
            await session.commit()
    except Exception as exc:
        logger.warning("mark_read_failed", error=str(exc))
    return {"status": "ok"}


@router.post("/read-all")
async def mark_all_notifications_read(
    db_session=None,
) -> dict[str, str]:
    """Mark all notifications as read."""
    if db_session is None:
        return {"status": "ok"}
    try:
        async with db_session() as session:
            await session.execute(
                text("UPDATE notifications SET is_read = TRUE WHERE is_read = FALSE")
            )
            await session.commit()
    except Exception as exc:
        logger.warning("mark_all_read_failed", error=str(exc))
    return {"status": "ok"}
