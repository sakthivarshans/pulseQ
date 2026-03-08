"""
connectors/gcp/collector.py
────────────────────────────
GCP cloud connector implementing CollectorInterface.
Collects metrics from: Cloud Monitoring, Cloud Logging, GKE, Billing.
Uses google-cloud-monitoring, google-cloud-logging, google-cloud-billing.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from shared.config import get_settings
from shared.interfaces import CollectorInterface
from shared.schemas import (
    CloudProvider,
    IntelligenceEvent,
    LogPayload,
    MetricPayload,
    AnomalyMetricType,
)

logger = structlog.get_logger(__name__)
settings = get_settings()


class GCPCollector(CollectorInterface):
    """
    Collects telemetry from GCP via Cloud Monitoring and Cloud Logging APIs.
    Authenticates with Application Default Credentials (ADC).
    """
    CLOUD_PROVIDER = CloudProvider.GCP

    def __init__(self) -> None:
        from google.cloud import monitoring_v3, logging_v2
        self._project_id = settings.gcp_project_id or ""
        self._monitoring = monitoring_v3.MetricServiceClient()
        self._logging = logging_v2.Client(project=self._project_id)
        self._project_name = f"projects/{self._project_id}"

    @property
    def provider_name(self) -> str:
        return "gcp"

    # ── High-level collect (convenience method used internally) ─────────────

    async def collect(self) -> list[IntelligenceEvent]:
        tasks = [
            asyncio.to_thread(self._collect_gce_metrics),
            asyncio.to_thread(self._collect_gke_metrics),
            asyncio.to_thread(self._collect_cloud_logs),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        events: list[IntelligenceEvent] = []
        for result in results:
            if isinstance(result, list):
                events.extend(result)
            elif isinstance(result, Exception):
                logger.warning("gcp_collection_partial_failure", error=str(result))
        return events

    # ── CollectorInterface abstract method implementations ───────────────────

    async def collect_metrics(
        self,
        service_names: list[str],
        start_time: str,
        end_time: str,
        metric_types: list[str] | None = None,
    ) -> list[IntelligenceEvent]:
        """Collect GCE and GKE metrics, optionally filtered by service name."""
        events = await asyncio.gather(
            asyncio.to_thread(self._collect_gce_metrics),
            asyncio.to_thread(self._collect_gke_metrics),
            return_exceptions=True,
        )
        all_events: list[IntelligenceEvent] = []
        for result in events:
            if isinstance(result, list):
                all_events.extend(result)
            elif isinstance(result, Exception):
                logger.warning("gcp_collect_metrics_partial_error", error=str(result))
        if service_names:
            all_events = [e for e in all_events if e.service_name in service_names]
        return all_events

    async def collect_logs(
        self,
        service_names: list[str],
        start_time: str,
        end_time: str,
        filter_pattern: str | None = None,
        max_events: int = 1000,
    ) -> list[IntelligenceEvent]:
        """Collect ERROR+ logs from Cloud Logging for the given time window."""
        try:
            events = await asyncio.to_thread(
                self._collect_cloud_logs_windowed,
                start_time,
                end_time,
                filter_pattern,
                max_events,
            )
            if service_names:
                events = [e for e in events if e.service_name in service_names]
            return events
        except Exception as exc:
            logger.warning("gcp_collect_logs_failed", error=str(exc))
            return []

    async def collect_traces(
        self,
        service_names: list[str],
        start_time: str,
        end_time: str,
    ) -> list[IntelligenceEvent]:
        """GCP trace collection — returns empty list (Cloud Trace requires separate SDK)."""
        logger.info("gcp_collect_traces_not_implemented")
        return []

    async def get_cost_data(self, lookback_days: int = 7) -> list[dict[str, Any]]:
        """Retrieve cost breakdown from GCP Billing export (BigQuery or Billing API)."""
        try:
            from google.cloud import billing_v1
            client = billing_v1.CloudBillingClient()
            account_name = f"billingAccounts/{settings.gcp_billing_account_id}"
            request = billing_v1.GetBillingAccountRequest(name=account_name)
            account = client.get_billing_account(request=request)
            return [
                {
                    "service_name": "gcp",
                    "amount_usd": 0.0,
                    "currency": "USD",
                    "period_start": (datetime.now(UTC) - timedelta(days=lookback_days)).isoformat(),
                    "period_end": datetime.now(UTC).isoformat(),
                    "account": account.name,
                    "note": "Detailed cost breakdown requires BigQuery Billing Export",
                }
            ]
        except Exception as exc:
            logger.warning("gcp_cost_data_failed", error=str(exc))
            return []

    async def health_check(self) -> dict[str, Any]:
        """Verify connectivity to GCP Cloud Monitoring API."""
        start = datetime.now(UTC)
        try:
            from google.cloud import monitoring_v3
            await asyncio.to_thread(
                self._monitoring.list_metric_descriptors,
                name=self._project_name,
                page_size=1,
            )
            latency_ms = (datetime.now(UTC) - start).total_seconds() * 1000
            return {"status": "ok", "latency_ms": round(latency_ms, 2), "error": None}
        except Exception as exc:
            latency_ms = (datetime.now(UTC) - start).total_seconds() * 1000
            return {"status": "error", "latency_ms": round(latency_ms, 2), "error": str(exc)}

    async def get_resource_inventory(self) -> list[dict[str, Any]]:
        try:
            from googleapiclient.discovery import build
            service = build("compute", "v1")
            request = service.instances().aggregatedList(project=self._project_id)
            instances = []
            while request is not None:
                response = request.execute()
                for zone_name, zone_data in response.get("items", {}).items():
                    for inst in zone_data.get("instances", []):
                        instances.append({
                            "type": "gce",
                            "id": inst.get("id"),
                            "name": inst.get("name"),
                            "zone": zone_name,
                            "machine_type": inst.get("machineType", "").split("/")[-1],
                            "status": inst.get("status"),
                        })
                request = service.instances().aggregatedList_next(request, response)
            return instances[:50]
        except Exception as exc:
            logger.warning("gcp_inventory_failed", error=str(exc))
            return []

    # ── Private sync helpers ─────────────────────────────────────────────────

    def _collect_gce_metrics(self) -> list[IntelligenceEvent]:
        """Collect GCE instance CPU utilization from Cloud Monitoring."""
        from google.cloud import monitoring_v3

        events: list[IntelligenceEvent] = []
        now = datetime.now(UTC)
        interval = monitoring_v3.TimeInterval()
        interval.start_time.FromDatetime(now - timedelta(minutes=5))
        interval.end_time.FromDatetime(now)

        metric_map = [
            ("compute.googleapis.com/instance/cpu/utilization", AnomalyMetricType.CPU),
            ("compute.googleapis.com/instance/memory/balloon/ram_used", AnomalyMetricType.MEMORY),
            ("compute.googleapis.com/instance/network/received_bytes_count", AnomalyMetricType.NETWORK_IO),
            ("compute.googleapis.com/instance/disk/write_ops_count", AnomalyMetricType.DISK_IO),
        ]
        for metric_type_str, anomaly_metric in metric_map:
            try:
                results = self._monitoring.list_time_series(
                    request={
                        "name": self._project_name,
                        "filter": f'metric.type="{metric_type_str}"',
                        "interval": interval,
                        "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
                        "page_size": 100,
                    }
                )
                for ts in results:
                    instance_name = ts.resource.labels.get("instance_id", "gce_instance")
                    zone = ts.resource.labels.get("zone", settings.gcp_default_region)
                    for point in ts.points:
                        value = (
                            point.value.double_value
                            or point.value.int64_value
                            or 0.0
                        )
                        if anomaly_metric == AnomalyMetricType.CPU:
                            value *= 100  # GCP CPU is 0-1
                        ts_dt = point.interval.end_time.ToDatetime().replace(tzinfo=UTC)
                        events.append(IntelligenceEvent(
                            event_type="metric",
                            source=f"gcp:{metric_type_str}",
                            service_name=instance_name,
                            environment=settings.default_environment,
                            cloud_provider=CloudProvider.GCP,
                            region=zone,
                            timestamp=ts_dt,
                            metric=MetricPayload(
                                metric_name=metric_type_str,
                                metric_type=anomaly_metric,
                                value=float(value),
                            ),
                        ))
            except Exception as exc:
                logger.warning("gcp_gce_metric_failed", metric=metric_type_str, error=str(exc))
        return events

    def _collect_gke_metrics(self) -> list[IntelligenceEvent]:
        """Collect GKE container CPU and memory utilization."""
        from google.cloud import monitoring_v3
        events: list[IntelligenceEvent] = []
        now = datetime.now(UTC)
        interval = monitoring_v3.TimeInterval()
        interval.start_time.FromDatetime(now - timedelta(minutes=5))
        interval.end_time.FromDatetime(now)
        gke_metrics = [
            ("kubernetes.io/container/cpu/core_usage_time", AnomalyMetricType.CPU),
            ("kubernetes.io/container/memory/used_bytes", AnomalyMetricType.MEMORY),
            ("kubernetes.io/pod/network/received_bytes_count", AnomalyMetricType.NETWORK_IO),
        ]
        for metric_str, anomaly_metric in gke_metrics:
            try:
                results = self._monitoring.list_time_series(
                    request={
                        "name": self._project_name,
                        "filter": f'metric.type="{metric_str}"',
                        "interval": interval,
                        "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
                        "page_size": 100,
                    }
                )
                for ts in results:
                    container = ts.resource.labels.get("container_name", "pod")
                    namespace = ts.resource.labels.get("namespace_name", "default")
                    svc_name = f"{namespace}/{container}"
                    for point in ts.points:
                        value = point.value.double_value or point.value.int64_value or 0.0
                        ts_dt = point.interval.end_time.ToDatetime().replace(tzinfo=UTC)
                        events.append(IntelligenceEvent(
                            event_type="metric",
                            source=f"gcp:gke:{container}",
                            service_name=svc_name,
                            environment=settings.default_environment,
                            cloud_provider=CloudProvider.GCP,
                            region=settings.gcp_default_region or "us-central1",
                            timestamp=ts_dt,
                            metric=MetricPayload(
                                metric_name=metric_str,
                                metric_type=anomaly_metric,
                                value=float(value),
                            ),
                        ))
            except Exception as exc:
                logger.warning("gcp_gke_metric_failed", metric=metric_str, error=str(exc))
        return events

    def _collect_cloud_logs(self) -> list[IntelligenceEvent]:
        """Collect ERROR severity logs from Cloud Logging (last 5 minutes)."""
        now = datetime.now(UTC)
        return self._collect_cloud_logs_windowed(
            start_time=(now - timedelta(minutes=5)).isoformat(),
            end_time=now.isoformat(),
        )

    def _collect_cloud_logs_windowed(
        self,
        start_time: str,
        end_time: str,
        filter_pattern: str | None = None,
        max_results: int = 50,
    ) -> list[IntelligenceEvent]:
        """Collect ERROR severity logs from Cloud Logging for an explicit window."""
        events: list[IntelligenceEvent] = []
        now = datetime.now(UTC)
        try:
            filter_str = (
                'severity>=ERROR '
                f'timestamp>="{start_time}" '
                f'timestamp<="{end_time}"'
            )
            if filter_pattern:
                filter_str += f' AND ({filter_pattern})'
            for entry in self._logging.list_entries(filter_=filter_str, max_results=max_results):
                svc = (
                    entry.resource.type
                    + (":" + entry.resource.labels.get("module_id", ""))
                    if hasattr(entry, "resource") else "gcp"
                )
                text = entry.payload if isinstance(entry.payload, str) else str(entry.payload)
                events.append(IntelligenceEvent(
                    event_type="log",
                    source="gcp:cloud_logging",
                    service_name=svc,
                    environment=settings.default_environment,
                    cloud_provider=CloudProvider.GCP,
                    region=settings.gcp_default_region or "us-central1",
                    timestamp=entry.timestamp if entry.timestamp else now,
                    log=LogPayload(
                        message=text[:1000],
                        level="ERROR",
                    ),
                ))
        except Exception as exc:
            logger.warning("gcp_cloud_log_collection_failed", error=str(exc))
        return events
