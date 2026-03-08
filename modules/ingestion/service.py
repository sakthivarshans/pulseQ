"""
modules/ingestion/service.py
─────────────────────────────
Ingestion Engine — main async service.

Responsibilities:
1. Polls all registered cloud connectors on configurable intervals
2. Receives OTel push data (forwarded by collector)
3. Normalizes all data into IntelligenceEvent via pipeline
4. Validates, deduplicates, and enriches with topology context
5. Publishes to Redis Streams: intelligence.events.raw
6. Manages connector failures with exponential backoff + dead letter queue
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import redis.asyncio as aioredis
import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from shared.config import get_settings
from shared.schemas import IntelligenceEvent

logger = structlog.get_logger(__name__)
settings = get_settings()

# Key prefix for deduplication in Redis
_DEDUPE_PREFIX = "neuralops:dedupe:"
_DEDUPE_TTL_SECONDS = 300  # 5 minutes


class IngestionService:
    """
    Core ingestion service. Instantiated once per process.
    Manages the lifecycle of all connectors and the ingestion pipeline.
    """

    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None
        self._connectors: list[Any] = []
        self._running = False
        self._ingested_count = 0
        self._error_count = 0
        self._dlq_count = 0
        self._started_at: datetime | None = None
        self._topology_cache: dict[str, dict[str, Any]] = {}

    async def start(self) -> None:
        """Initialize Redis connection, load topology, register connectors."""
        try:
            self._redis = aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=20,
            )
            await self._redis.ping()
            logger.info("ingestion_redis_connected")
            # Ensure consumer group exists
            await self._ensure_stream_group(settings.redis_stream_raw_events)
            # Load service topology from DB (bootstrapped from config or previous runs)
            await self._load_topology_cache()
        except Exception as exc:
            logger.warning("ingestion_redis_unavailable_continuing", error=str(exc))
            self._redis = None

        # Register enabled cloud connectors
        self._register_connectors()

        self._running = True
        self._started_at = datetime.now(UTC)
        logger.info("ingestion_service_started", connectors=len(self._connectors))

    async def stop(self) -> None:
        self._running = False
        if self._redis:
            await self._redis.aclose()
        logger.info("ingestion_service_stopped")

    def _register_connectors(self) -> None:
        """Register all enabled cloud connectors."""
        if settings.github_enabled and settings.github_token:
            from connectors.github.collector import GitHubCollector
            self._connectors.append(GitHubCollector())
            logger.info("connector_registered", provider="github",
                        repos=settings.github_monitored_repos)

        if settings.aws_enabled:
            from connectors.aws.collector import AWSCollector
            self._connectors.append(AWSCollector())
            logger.info("connector_registered", provider="aws")

        if settings.azure_enabled:
            from connectors.azure.collector import AzureCollector
            self._connectors.append(AzureCollector())
            logger.info("connector_registered", provider="azure")

        if settings.gcp_enabled:
            from connectors.gcp.collector import GCPCollector
            self._connectors.append(GCPCollector())
            logger.info("connector_registered", provider="gcp")

    async def _ensure_stream_group(self, stream: str) -> None:
        """Create Redis Stream consumer group if not exists (MKSTREAM)."""
        assert self._redis is not None
        try:
            await self._redis.xgroup_create(
                stream,
                settings.redis_consumer_group,
                id="$",
                mkstream=True,
            )
            logger.info("stream_group_created", stream=stream)
        except aioredis.ResponseError as exc:
            if "BUSYGROUP" in str(exc):
                logger.debug("stream_group_exists", stream=stream)
            else:
                raise

    async def _load_topology_cache(self) -> None:
        """
        Load service topology from Redis cache or initialize with defaults.
        In production this is populated by the API module when users configure services.
        """
        assert self._redis is not None
        topology_raw = await self._redis.get("neuralops:topology:cache")
        if topology_raw:
            self._topology_cache = json.loads(topology_raw)
            logger.info("topology_cache_loaded", services=len(self._topology_cache))
        else:
            logger.info("topology_cache_empty")

    async def run_collection_loop(self) -> None:
        """
        Main polling loop — runs all connectors on configurable intervals.
        Each connector gets its own task with independent failure handling.
        """
        while self._running:
            end_time = datetime.now(UTC).isoformat()
            start_time = (
                datetime.now(UTC) - timedelta(seconds=settings.connector_poll_interval_seconds)
            ).isoformat()

            tasks = [
                self._run_connector_safely(connector, start_time, end_time)
                for connector in self._connectors
            ]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

            await asyncio.sleep(settings.connector_poll_interval_seconds)

    async def _run_connector_safely(
        self,
        connector: Any,
        start_time: str,
        end_time: str,
    ) -> None:
        """Run a single connector with exponential backoff retry.
        Supports both interface styles:
          - New: connector.collect() -> list[IntelligenceEvent]
          - Legacy: connector.collect_metrics() + connector.collect_logs()
        """
        provider = getattr(connector, "provider_name", "unknown")
        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception_type(Exception),
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=2, max=30),
            ):
                with attempt:
                    # Support both connector interface styles
                    if hasattr(connector, "collect"):
                        all_events = await connector.collect()
                    else:
                        events = await connector.collect_metrics(
                            service_names=[],
                            start_time=start_time,
                            end_time=end_time,
                        )
                        log_events = await connector.collect_logs(
                            service_names=[],
                            start_time=start_time,
                            end_time=end_time,
                        )
                        all_events = events + log_events

                    await self.publish_events(all_events)
                    logger.info(
                        "connector_poll_success",
                        provider=provider,
                        events=len(all_events),
                    )
        except Exception as exc:
            self._error_count += 1
            logger.error(
                "connector_poll_failed",
                provider=provider,
                error=str(exc),
            )
            # Only send to DLQ if Redis is available
            if self._redis is not None:
                await self._send_to_dlq(
                    provider=provider,
                    error=str(exc),
                    timestamp=datetime.now(UTC).isoformat(),
                )

    async def publish_events(self, events: list[IntelligenceEvent]) -> int:
        """
        Validate, deduplicate, enrich, and publish events to Redis Stream.
        If Redis is unavailable, logs event counts only (graceful degradation).
        Returns the count of events actually published.
        """
        if not events:
            return 0

        # Graceful degradation: if Redis is down, just count and log
        if self._redis is None:
            logger.debug(
                "publish_skipped_no_redis",
                event_count=len(events),
                hint="start Docker to enable Redis stream publishing",
            )
            return 0

        published = 0
        for event in events:
            try:
                # Deduplication check
                if await self._is_duplicate(event):
                    continue

                # Enrich with topology
                enriched = self._enrich_topology(event)

                # Publish to Redis Stream
                event_dict = enriched.model_dump(mode="json")
                await self._redis.xadd(
                    settings.redis_stream_raw_events,
                    {
                        "event_id": event_dict["event_id"],
                        "event_type": event_dict["event_type"],
                        "service_name": event_dict["service_name"],
                        "payload": json.dumps(event_dict),
                    },
                    maxlen=100_000,
                    approximate=True,
                )

                await self._mark_seen(event)
                published += 1
                self._ingested_count += 1

            except Exception as exc:
                self._error_count += 1
                logger.error("event_publish_failed", event_id=event.event_id, error=str(exc))

        return published

    def _compute_dedupe_key(self, event: IntelligenceEvent) -> str:
        """Compute a stable deduplicate hash for an event."""
        if event.dedupe_key:
            return event.dedupe_key
        parts = [
            event.service_name,
            event.event_type,
            event.source,
            str(event.timestamp.replace(microsecond=0, tzinfo=None)),
        ]
        if event.metric:
            parts.append(f"{event.metric.metric_name}:{event.metric.value}")
        raw = ":".join(parts).encode()
        return hashlib.sha256(raw).hexdigest()[:16]

    async def _is_duplicate(self, event: IntelligenceEvent) -> bool:
        if self._redis is None:
            return False  # no dedup without Redis — allow all events through
        key = _DEDUPE_PREFIX + self._compute_dedupe_key(event)
        result = await self._redis.exists(key)
        return bool(result)

    async def _mark_seen(self, event: IntelligenceEvent) -> None:
        if self._redis is None:
            return
        key = _DEDUPE_PREFIX + self._compute_dedupe_key(event)
        await self._redis.setex(key, _DEDUPE_TTL_SECONDS, "1")

    def _enrich_topology(self, event: IntelligenceEvent) -> IntelligenceEvent:
        """Attach topology context if available in the cache."""
        if event.service_name in self._topology_cache:
            from shared.schemas import ServiceTopology
            topo_data = self._topology_cache[event.service_name]
            event = event.model_copy(
                update={"topology": ServiceTopology(**topo_data)}
            )
        return event

    async def _send_to_dlq(self, **kwargs: Any) -> None:
        """Push failed collection record to dead-letter queue."""
        if self._redis is None:
            return  # DLQ requires Redis — skip silently
        self._dlq_count += 1
        await self._redis.xadd(
            "neuralops:dlq:ingestion",
            {k: str(v) for k, v in kwargs.items()},
            maxlen=10_000,
            approximate=True,
        )

    def get_stats(self) -> dict[str, Any]:
        return {
            "ingested_total": self._ingested_count,
            "error_total": self._error_count,
            "dlq_total": self._dlq_count,
            "connectors": len(self._connectors),
            "uptime_seconds": (
                (datetime.now(UTC) - self._started_at).total_seconds()
                if self._started_at
                else 0
            ),
        }
