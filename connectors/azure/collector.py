"""
connectors/azure/collector.py
──────────────────────────────
Azure cloud connector implementing CollectorInterface.
Collects metrics from: Azure Monitor, AKS, VMs, Cost Management.
Uses azure-monitor-query, azure-mgmt-compute, azure-identity.
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
    LogEvent,
    LogSeverity,
    MetricEvent,
    AnomalyMetricType,
)

logger = structlog.get_logger(__name__)
settings = get_settings()


class AzureCollector(CollectorInterface):
    """
    Collects telemetry from Azure Monitor and compute services.
    Authenticates via DefaultAzureCredential (env vars, managed identity, or CLI).
    """
    CLOUD_PROVIDER = CloudProvider.AZURE

    def __init__(self) -> None:
        from azure.identity import DefaultAzureCredential
        from azure.monitor.query import MetricsQueryClient, LogsQueryClient
        self._credential = DefaultAzureCredential()
        self._metrics_client = MetricsQueryClient(self._credential)
        self._logs_client = LogsQueryClient(self._credential)
        self._subscription_id = settings.azure_subscription_id or ""
        self._resource_group = settings.azure_resource_group or ""
        self._workspace_id = settings.azure_log_analytics_workspace_id or ""

    async def collect(self) -> list[IntelligenceEvent]:
        tasks = [
            asyncio.to_thread(self._collect_vm_metrics),
            asyncio.to_thread(self._collect_log_analytics_errors),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        events: list[IntelligenceEvent] = []
        for result in results:
            if isinstance(result, list):
                events.extend(result)
            elif isinstance(result, Exception):
                logger.warning("azure_collection_partial_failure", error=str(result))
        return events

    async def health_check(self) -> bool:
        try:
            from azure.mgmt.resource import ResourceManagementClient
            client = ResourceManagementClient(self._credential, self._subscription_id)
            next(iter(client.resource_groups.list()), None)
            return True
        except Exception:
            return False

    async def get_resource_inventory(self) -> list[dict[str, Any]]:
        try:
            from azure.mgmt.compute import ComputeManagementClient
            client = ComputeManagementClient(self._credential, self._subscription_id)
            vms = []
            for vm in client.virtual_machines.list_all():
                vms.append({
                    "type": "azure_vm",
                    "id": vm.id,
                    "name": vm.name,
                    "location": vm.location,
                    "vm_size": vm.hardware_profile.vm_size if vm.hardware_profile else "Unknown",
                })
            return vms[:50]
        except Exception as exc:
            logger.warning("azure_inventory_failed", error=str(exc))
            return []

    def _collect_vm_metrics(self) -> list[IntelligenceEvent]:
        events: list[IntelligenceEvent] = []
        try:
            from azure.mgmt.compute import ComputeManagementClient
            from azure.monitor.query import MetricAggregationType
            from datetime import UTC, datetime
            comp_client = ComputeManagementClient(self._credential, self._subscription_id)
            now = datetime.now(UTC)
            timespan = timedelta(minutes=5)
            for vm in comp_client.virtual_machines.list_all():
                resource_id = vm.id
                try:
                    resp = self._metrics_client.query_resource(
                        resource_uri=resource_id,
                        metric_names=["Percentage CPU", "Available Memory Bytes", "Network In Total"],
                        timespan=(now - timespan, now),
                        granularity=timedelta(minutes=1),
                        aggregations=[MetricAggregationType.AVERAGE],
                    )
                    metric_type_map = {
                        "Percentage CPU": AnomalyMetricType.CPU,
                        "Available Memory Bytes": AnomalyMetricType.MEMORY,
                        "Network In Total": AnomalyMetricType.NETWORK_IN,
                    }
                    for metric in resp.metrics:
                        mtype = metric_type_map.get(metric.name, AnomalyMetricType.CPU)
                        for ts in metric.timeseries:
                            for dp in ts.data:
                                if dp.average is not None:
                                    value = dp.average
                                    if metric.name == "Available Memory Bytes":
                                        # Convert to utilization percentage (approx 8GB)
                                        total_bytes = 8 * 1024**3
                                        value = (1 - dp.average / total_bytes) * 100
                                    events.append(IntelligenceEvent(
                                        event_type="metric",
                                        source=f"azure:monitor:{vm.name}",
                                        service_name=vm.name or "azure_vm",
                                        environment=settings.default_environment,
                                        cloud_provider=CloudProvider.AZURE,
                                        region=vm.location or "unknown",
                                        timestamp=dp.timestamp or datetime.now(UTC),
                                        metric=MetricEvent(
                                            metric_type=mtype,
                                            value=float(value),
                                            service_name=vm.name or "azure_vm",
                                            environment=settings.default_environment,
                                        ),
                                    ))
                except Exception as exc:
                    logger.warning("azure_vm_metric_failed", vm=vm.name, error=str(exc))
        except Exception as exc:
            logger.warning("azure_vm_collection_failed", error=str(exc))
        return events

    def _collect_log_analytics_errors(self) -> list[IntelligenceEvent]:
        """Query Log Analytics workspace for recent errors."""
        events: list[IntelligenceEvent] = []
        if not self._workspace_id:
            return events
        try:
            from azure.monitor.query import LogsQueryStatus
            query = """
                AzureDiagnostics
                | where Level == "Error" or Level == "Warning"
                | project TimeGenerated, Resource, Level, Message = iff(isempty(Message), ResultDescription, Message)
                | order by TimeGenerated desc
                | limit 50
            """
            from datetime import timedelta
            resp = self._logs_client.query_workspace(
                workspace_id=self._workspace_id,
                query=query,
                timespan=timedelta(minutes=10),
            )
            if resp.status == LogsQueryStatus.SUCCESS and resp.tables:
                for row in resp.tables[0].rows:
                    ts_val, resource, level, message = row[0], row[1], row[2], row[3]
                    events.append(IntelligenceEvent(
                        event_type="log",
                        source="azure:log_analytics",
                        service_name=str(resource or "azure"),
                        environment=settings.default_environment,
                        cloud_provider=CloudProvider.AZURE,
                        region="global",
                        timestamp=ts_val if isinstance(ts_val, datetime) else datetime.now(UTC),
                        log=LogEvent(
                            level=LogSeverity.ERROR if level == "Error" else LogSeverity.WARN,
                            message=str(message or "")[:1000],
                            service_name=str(resource or "azure"),
                            environment=settings.default_environment,
                        ),
                    ))
        except Exception as exc:
            logger.warning("azure_log_analytics_failed", error=str(exc))
        return events
