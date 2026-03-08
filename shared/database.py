"""
shared/database.py
──────────────────
Central Motor (async MongoDB) client initialization.
Called once from the API lifespan startup event.

Exports:
  init_mongodb(settings) -> motor database object
  get_mongo_db()         -> returns the active database (call after init)
"""
from __future__ import annotations

import logging
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

try:
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
    _MOTOR_OK = True
except ImportError:
    _MOTOR_OK = False
    AsyncIOMotorClient = None  # type: ignore
    AsyncIOMotorDatabase = None  # type: ignore

# Module-level singletons — set by init_mongodb()
_motor_client: Any = None
_mongo_db: Any = None


async def init_mongodb(settings: Any) -> Any:
    """
    Initialize the Motor async client, create all required indexes,
    and return the database handle.

    Idempotent: calling multiple times is safe (re-uses existing client).
    """
    global _motor_client, _mongo_db

    if not _MOTOR_OK:
        logger.warning("motor_not_installed", msg="motor package not available — MongoDB disabled")
        return None

    if _motor_client is not None:
        return _mongo_db

    try:
        _motor_client = AsyncIOMotorClient(
            settings.mongodb_url,
            serverSelectionTimeoutMS=10_000,
            connectTimeoutMS=10_000,
        )
        _mongo_db = _motor_client[settings.mongodb_db_name]

        # Verify connectivity
        await _motor_client.admin.command("ping")
        logger.info("mongodb_connected", db=settings.mongodb_db_name)

        # ── Create indexes (idempotent) ────────────────────────────────────
        # repo_errors — primary lookup patterns
        await _mongo_db["repo_errors"].create_index(
            [("repo_id", 1), ("file_path", 1)], background=True
        )
        await _mongo_db["repo_errors"].create_index(
            [("repo_id", 1), ("severity", 1)], background=True
        )
        await _mongo_db["repo_errors"].create_index(
            [("repo_id", 1), ("is_resolved", 1)], background=True
        )
        await _mongo_db["repo_errors"].create_index(
            [("repo_id", 1), ("created_at", -1)], background=True
        )

        # error_feedback — one vote per user per error (unique compound index)
        await _mongo_db["error_feedback"].create_index(
            [("error_id", 1), ("user_id", 1)], unique=True, background=True
        )

        # rl_weights — one doc per error_type
        await _mongo_db["rl_weights"].create_index(
            "error_type", unique=True, background=True
        )

        # chatbot_context_cache — TTL of 300 seconds
        await _mongo_db["chatbot_context_cache"].create_index(
            "created_at", expireAfterSeconds=300, background=True
        )

        # model_evaluations — sort by date
        await _mongo_db["model_evaluations"].create_index(
            [("evaluated_at", -1)], background=True
        )

        logger.info("mongodb_indexes_created")
        return _mongo_db

    except Exception as exc:
        logger.error("mongodb_init_failed", error=str(exc))
        _motor_client = None
        _mongo_db = None
        return None


def get_mongo_db() -> Any:
    """Return the active Motor database handle (None if not initialized)."""
    return _mongo_db


async def close_mongodb() -> None:
    """Close the Motor client — called from lifespan shutdown."""
    global _motor_client, _mongo_db
    if _motor_client is not None:
        _motor_client.close()
        _motor_client = None
        _mongo_db = None
        logger.info("mongodb_closed")
