"""
modules/api/services/error_service.py
──────────────────────────────────────
All MongoDB CRUD operations for code errors detected by Phi-3.
Handles: get_errors, get_single_error, save_errors_batch,
         process_feedback, update_rl_weights.

RL weight formula:
  new_threshold = clamp(0.5 + (downvote_ratio - upvote_ratio) * 0.3, 0.2, 0.8)
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

try:
    from bson import ObjectId
    from bson.errors import InvalidId
    _BSON_OK = True
except ImportError:
    _BSON_OK = False
    ObjectId = None  # type: ignore


def _oid_to_str(doc: dict) -> dict:
    """Convert ObjectId fields to strings for JSON serialization."""
    if doc is None:
        return doc
    out = dict(doc)
    if "_id" in out and _BSON_OK and isinstance(out["_id"], ObjectId):
        out["error_id"] = str(out["_id"])
        del out["_id"]
    return out


async def get_errors_for_repo(
    mongo_db: Any,
    repo_id: str,
    severity: str | None = None,
    error_type: str | None = None,
    file_path: str | None = None,
    is_resolved: bool | None = None,
    limit: int = 200,
    skip: int = 0,
) -> dict:
    """
    Fetch errors for a repo from MongoDB with optional filters.
    Returns {"errors": [...], "total": int}.
    """
    if mongo_db is None:
        return {"errors": [], "total": 0}

    query: dict[str, Any] = {"repo_id": repo_id}
    if severity:
        query["severity"] = severity
    if error_type:
        query["error_type"] = error_type
    if file_path:
        query["file_path"] = {"$regex": file_path, "$options": "i"}
    if is_resolved is not None:
        query["is_resolved"] = is_resolved
    else:
        # Default: only show unresolved
        query["is_resolved"] = {"$ne": True}

    try:
        total = await mongo_db["repo_errors"].count_documents(query)
        cursor = (
            mongo_db["repo_errors"]
            .find(query)
            .sort([("severity", 1), ("confidence_score", -1)])
            .skip(skip)
            .limit(limit)
        )
        errors = []
        async for doc in cursor:
            errors.append(_oid_to_str(doc))
        return {"errors": errors, "total": total}
    except Exception as exc:
        logger.error("get_errors_for_repo_failed", repo_id=repo_id, error=str(exc))
        return {"errors": [], "total": 0}


async def get_single_error(mongo_db: Any, repo_id: str, error_id: str) -> dict | None:
    """Fetch a single error document by its ObjectId string."""
    if mongo_db is None or not _BSON_OK:
        return None
    try:
        oid = ObjectId(error_id)
    except Exception:
        return None
    try:
        doc = await mongo_db["repo_errors"].find_one({"_id": oid, "repo_id": repo_id})
        return _oid_to_str(doc) if doc else None
    except Exception as exc:
        logger.error("get_single_error_failed", error_id=error_id, error=str(exc))
        return None


async def save_errors_batch(
    mongo_db: Any,
    repo_id: str,
    repo_name: str,
    analysis_id: str,
    errors: list[dict],
) -> int:
    """
    Persist a batch of detected errors to MongoDB.
    Deletes all previous errors for this repo before inserting the new batch
    so re-scans produce fresh results.
    Returns the number of documents inserted.
    """
    if mongo_db is None or not errors:
        return 0

    now = datetime.now(UTC)
    docs = []
    for err in errors:
        docs.append({
            "repo_id": repo_id,
            "repo_name": repo_name,
            "analysis_id": analysis_id,
            "file_path": str(err.get("file_path", err.get("file", ""))),
            "line_number": int(err.get("line_number", 1)),
            "language": str(err.get("language", "")),
            "error_type": str(err.get("error_type", err.get("issue_type", "unknown"))),
            "severity": str(err.get("severity", "P3")),
            "title": str(err.get("title", err.get("description", "")))[:200],
            "description": str(err.get("description", "")),
            "suggestion": str(err.get("suggestion", "")),
            "code_before": str(err.get("code_before", ""))[:2000],
            "code_after": str(err.get("code_after", ""))[:2000],
            "confidence_score": float(err.get("confidence_score", 0.8)),
            "source": str(err.get("source", "static")),
            "upvotes": 0,
            "downvotes": 0,
            "is_resolved": False,
            "created_at": now,
        })

    try:
        # Remove previous scan results for this repo
        await mongo_db["repo_errors"].delete_many({"repo_id": repo_id})
        result = await mongo_db["repo_errors"].insert_many(docs, ordered=False)
        count = len(result.inserted_ids)
        logger.info("errors_saved_to_mongo", repo_id=repo_id, count=count)
        return count
    except Exception as exc:
        logger.error("save_errors_batch_failed", repo_id=repo_id, error=str(exc))
        return 0


async def process_feedback(
    mongo_db: Any,
    repo_id: str,
    error_id: str,
    user_id: str,
    feedback: str,  # "upvote" or "downvote"
) -> dict:
    """
    Increment the upvote/downvote counter on the error document.
    Inserts a record into error_feedback using a unique index (error_id + user_id)
    to prevent duplicate votes.
    Returns the updated counts.
    """
    if mongo_db is None or not _BSON_OK:
        return {"error": "MongoDB not available"}

    try:
        oid = ObjectId(error_id)
    except Exception:
        return {"error": "Invalid error_id"}

    # Try to record this user's vote (unique index prevents duplicates)
    try:
        await mongo_db["error_feedback"].insert_one({
            "error_id": oid,
            "repo_id": repo_id,
            "user_id": user_id,
            "feedback": feedback,
            "created_at": datetime.now(UTC),
        })
    except Exception:
        # Duplicate key — user already voted
        return {"error": "Already voted", "already_voted": True}

    # Increment the counter on the error document
    field = "upvotes" if feedback == "upvote" else "downvotes"
    result = await mongo_db["repo_errors"].find_one_and_update(
        {"_id": oid},
        {"$inc": {field: 1}},
        return_document=True,
        projection={"upvotes": 1, "downvotes": 1, "error_type": 1},
    )
    if not result:
        return {"error": "Error document not found"}

    return {
        "upvotes": result.get("upvotes", 0),
        "downvotes": result.get("downvotes", 0),
        "feedback_recorded": feedback,
    }


async def update_rl_weights(mongo_db: Any, error_type: str, mongo_db_ref: Any = None) -> float:
    """
    Recalculate and upsert the RL confidence threshold for an error_type.

    Formula:
      total = upvotes + downvotes (across all errors of this type)
      upvote_ratio   = upvotes / total  (0.0 if no votes)
      downvote_ratio = downvotes / total
      threshold = clamp(0.5 + (downvote_ratio - upvote_ratio) * 0.3, 0.2, 0.8)
    """
    db = mongo_db if mongo_db is not None else mongo_db_ref
    if db is None:
        return 0.5

    try:
        # Aggregate all votes across errors of this type
        pipeline = [
            {"$match": {"error_type": error_type}},
            {"$group": {
                "_id": "$error_type",
                "total_upvotes": {"$sum": "$upvotes"},
                "total_downvotes": {"$sum": "$downvotes"},
            }},
        ]
        async for agg in db["repo_errors"].aggregate(pipeline):
            up = agg.get("total_upvotes", 0)
            down = agg.get("total_downvotes", 0)
            total = up + down
            if total == 0:
                new_threshold = 0.5
            else:
                up_ratio = up / total
                down_ratio = down / total
                new_threshold = 0.5 + (down_ratio - up_ratio) * 0.3
                new_threshold = max(0.2, min(0.8, new_threshold))

            await db["rl_weights"].update_one(
                {"error_type": error_type},
                {"$set": {
                    "confidence_threshold": round(new_threshold, 4),
                    "total_upvotes": up,
                    "total_downvotes": down,
                    "last_updated": datetime.now(UTC),
                }},
                upsert=True,
            )
            logger.info("rl_weight_updated", error_type=error_type, threshold=new_threshold)
            return round(new_threshold, 4)

        # No errors exist for this type yet — set default
        await db["rl_weights"].update_one(
            {"error_type": error_type},
            {"$setOnInsert": {
                "confidence_threshold": 0.5,
                "total_upvotes": 0,
                "total_downvotes": 0,
                "last_updated": datetime.now(UTC),
            }},
            upsert=True,
        )
        return 0.5

    except Exception as exc:
        logger.error("update_rl_weights_failed", error_type=error_type, error=str(exc))
        return 0.5


async def resolve_error(mongo_db: Any, repo_id: str, error_id: str) -> bool:
    """Mark a single error document as resolved. Returns True on success."""
    if mongo_db is None or not _BSON_OK:
        return False
    try:
        oid = ObjectId(error_id)
        result = await mongo_db["repo_errors"].update_one(
            {"_id": oid, "repo_id": repo_id},
            {"$set": {"is_resolved": True, "resolved_at": datetime.now(UTC)}},
        )
        return result.modified_count > 0
    except Exception as exc:
        logger.error("resolve_error_failed", error_id=error_id, error=str(exc))
        return False
