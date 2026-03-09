"""
modules/api/background/website_monitor.py
──────────────────────────────────────────
Background task that polls website URLs every 60 seconds.
Reads configured URLs from PostgreSQL `repositories` table and
inserts check results into `website_checks` table.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, UTC
from typing import Any

import httpx
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

logger = structlog.get_logger(__name__)

_POLL_INTERVAL_SECONDS = 60
_HTTP_TIMEOUT = 10.0


async def poll_websites(session_factory: async_sessionmaker) -> None:
    """Continuously poll all repositories that have a website_url and live monitoring enabled."""
    _missing_table_logged = False
    while True:
        try:
            await _run_all_checks(session_factory)
            _missing_table_logged = False  # reset if it starts working
        except asyncio.CancelledError:
            break
        except Exception as exc:
            err = str(exc)
            # Silently back off if the table doesn't exist yet (local dev without migrations)
            if "UndefinedTableError" in err or "does not exist" in err:
                if not _missing_table_logged:
                    logger.info(
                        "website_monitor_waiting_for_schema",
                        reason="repositories table not found — run init.sql to enable website monitoring",
                    )
                    _missing_table_logged = True
                await asyncio.sleep(300)  # wait 5 min before retrying
                continue
            logger.warning("website_monitor_loop_error", error=err)
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)


async def _run_all_checks(session_factory: async_sessionmaker) -> None:
    async with session_factory() as session:
        result = await session.execute(
            text(
                "SELECT id, website_url FROM repositories "
                "WHERE website_url IS NOT NULL AND website_url != '' "
                "  AND is_live_monitoring_enabled = TRUE"
            )
        )
        repos = result.mappings().all()

    if not repos:
        return

    tasks = [_check_one(repo["id"], repo["website_url"], session_factory) for repo in repos]
    await asyncio.gather(*tasks, return_exceptions=True)


async def _check_one(repo_id: Any, url: str, session_factory: async_sessionmaker) -> None:
    status_code: int | None = None
    response_time_ms: float | None = None
    is_up = False

    try:
        start = asyncio.get_event_loop().time()
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
            response = await client.get(url)
            elapsed = asyncio.get_event_loop().time() - start
            status_code = response.status_code
            response_time_ms = round(elapsed * 1000, 2)
            is_up = 200 <= response.status_code < 400
    except httpx.TimeoutException:
        status_code = 0
        response_time_ms = _HTTP_TIMEOUT * 1000
        is_up = False
    except Exception as exc:
        logger.debug("website_check_error", url=url, error=str(exc))
        status_code = 0
        response_time_ms = None
        is_up = False

    try:
        async with session_factory() as session:
            await session.execute(
                text(
                    "INSERT INTO website_checks (repo_id, url, status_code, response_time_ms, is_up, checked_at) "
                    "VALUES (:repo_id, :url, :status_code, :response_time_ms, :is_up, :checked_at)"
                ),
                {
                    "repo_id": repo_id,
                    "url": url,
                    "status_code": status_code,
                    "response_time_ms": response_time_ms,
                    "is_up": is_up,
                    "checked_at": datetime.now(UTC),
                },
            )
            await session.commit()
        logger.debug("website_check_done", url=url, status=status_code, up=is_up, ms=response_time_ms)
    except Exception as exc:
        logger.warning("website_check_insert_failed", url=url, error=str(exc))
