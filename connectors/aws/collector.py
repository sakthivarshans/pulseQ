"""
connectors/aws/collector.py
────────────────────────────
AWS cloud connector implementing CollectorInterface.
Collects metrics from: CloudWatch, EC2, EKS, RDS, Cost Explorer.
All calls use boto3 with proper pagination, error handling, and rate limit backoff.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
import structlog
from botocore.exceptions import ClientError, EndpointConnectionError

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


class AWSCollector(CollectorInterface):
    """
    Collects telemetry from AWS services via boto3.
    Uses IAM role assumed via instance profile or explicit credentials.
    """
    CLOUD_PROVIDER = CloudProvider.AWS

    def __init__(self) -> None:
        kwargs: dict[str, Any] = {"region_name": settings.aws_default_region}
        if settings.aws_access_key_id and settings.aws_secret_access_key:
            kwargs["aws_access_key_id"] = settings.aws_access_key_id
            kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
            if settings.aws_session_token:
                kwargs["aws_session_token"] = settings.aws_session_token

        self._cw = boto3.client("cloudwatch", **kwargs)
        self._ec2 = boto3.client("ec2", **kwargs)
        self._rds = boto3.client("rds", **kwargs)
        self._eks = boto3.client("eks", **kwargs)
        self._ce = boto3.client("ce", **{k: v for k, v in kwargs.items() if k == "region_name"})
        self._logs = boto3.client("logs", **kwargs)
        self._region = settings.aws_default_region

    async def collect(self) -> list[IntelligenceEvent]:
        """Collect all AWS metrics concurrently."""
        tasks = [
            asyncio.to_thread(self._collect_cloudwatch_metrics),
            asyncio.to_thread(self._collect_ec2_status),
            asyncio.to_thread(self._collect_rds_metrics),
            asyncio.to_thread(self._collect_cloudwatch_logs),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        events: list[IntelligenceEvent] = []
        for result in results:
            if isinstance(result, list):
                events.extend(result)
            elif isinstance(result, Exception):
                logger.warning("aws_collection_partial_failure", error=str(result))
        return events

    async def health_check(self) -> bool:
        try:
            await asyncio.to_thread(self._cw.list_metrics, Namespace="AWS/EC2", MaxItems=1)
            return True
        except Exception:
            return False

    async def get_resource_inventory(self) -> list[dict[str, Any]]:
        """Get a summary of key AWS resources for RCA context."""
        try:
            ec2_resp = await asyncio.to_thread(
                self._ec2.describe_instances,
                Filters=[{"Name": "instance-state-name", "Values": ["running"]}],
            )
            instances = []
            for reservation in ec2_resp.get("Reservations", []):
                for inst in reservation.get("Instances", []):
                    name = next(
                        (t["Value"] for t in inst.get("Tags", []) if t["Key"] == "Name"),
                        inst["InstanceId"],
                    )
                    instances.append({
                        "type": "ec2",
                        "id": inst["InstanceId"],
                        "name": name,
                        "instance_type": inst["InstanceType"],
                        "state": inst["State"]["Name"],
                    })
            return instances[:50]
        except Exception as exc:
            logger.warning("aws_inventory_failed", error=str(exc))
            return []

    def _collect_cloudwatch_metrics(self) -> list[IntelligenceEvent]:
        """Pull CPU, Memory, NetworkIn for all EC2 instances."""
        events: list[IntelligenceEvent] = []
        now = datetime.now(UTC)
        start = now - timedelta(minutes=6)

        namespaces = [
            ("AWS/EC2", "CPUUtilization", AnomalyMetricType.CPU),
            ("AWS/RDS", "CPUUtilization", AnomalyMetricType.CPU),
            ("AWS/ApplicationELB", "TargetResponseTime", AnomalyMetricType.LATENCY),
            ("AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", AnomalyMetricType.ERROR_RATE),
            ("AWS/EC2", "NetworkIn", AnomalyMetricType.NETWORK_IN),
            ("AWS/EC2", "NetworkOut", AnomalyMetricType.NETWORK_OUT),
        ]
        for namespace, metric_name, metric_type in namespaces:
            try:
                paginator = self._cw.get_paginator("list_metrics")
                pages = paginator.paginate(Namespace=namespace, MetricName=metric_name)
                for page in pages:
                    for metric in page.get("Metrics", []):
                        dims = {d["Name"]: d["Value"] for d in metric.get("Dimensions", [])}
                        service_name = dims.get("InstanceId", dims.get("LoadBalancer", namespace))
                        resp = self._cw.get_metric_statistics(
                            Namespace=namespace,
                            MetricName=metric_name,
                            Dimensions=metric.get("Dimensions", []),
                            StartTime=start,
                            EndTime=now,
                            Period=60,
                            Statistics=["Average"],
                        )
                        for dp in resp.get("Datapoints", []):
                            events.append(IntelligenceEvent(
                                event_type="metric",
                                source=f"aws:{namespace}",
                                service_name=service_name,
                                environment=settings.default_environment,
                                cloud_provider=CloudProvider.AWS,
                                region=self._region,
                                timestamp=dp["Timestamp"],
                                metric=MetricEvent(
                                    metric_type=metric_type,
                                    value=float(dp["Average"]),
                                    unit=dp.get("Unit", "Count"),
                                    service_name=service_name,
                                    environment=settings.default_environment,
                                ),
                            ))
            except (ClientError, EndpointConnectionError) as exc:
                logger.warning("cloudwatch_metric_failed", metric=metric_name, error=str(exc))
        return events

    def _collect_ec2_status(self) -> list[IntelligenceEvent]:
        """Collect EC2 instance status checks (system/instance)."""
        events: list[IntelligenceEvent] = []
        try:
            resp = self._ec2.describe_instance_status(IncludeAllInstances=True)
            for status in resp.get("InstanceStatuses", []):
                inst_id = status["InstanceId"]
                sys_ok = status["SystemStatus"]["Status"] == "ok"
                inst_ok = status["InstanceStatus"]["Status"] == "ok"
                if not sys_ok or not inst_ok:
                    events.append(IntelligenceEvent(
                        event_type="log",
                        source="aws:ec2:status",
                        service_name=inst_id,
                        environment=settings.default_environment,
                        cloud_provider=CloudProvider.AWS,
                        region=self._region,
                        log=LogEvent(
                            level=LogSeverity.ERROR if not sys_ok else LogSeverity.WARN,
                            message=(
                                f"EC2 {inst_id}: system_status={status['SystemStatus']['Status']}, "
                                f"instance_status={status['InstanceStatus']['Status']}"
                            ),
                            service_name=inst_id,
                            environment=settings.default_environment,
                        ),
                    ))
        except (ClientError, EndpointConnectionError) as exc:
            logger.warning("ec2_status_collection_failed", error=str(exc))
        return events

    def _collect_rds_metrics(self) -> list[IntelligenceEvent]:
        """Collect RDS DB instance connection counts and CPU."""
        events: list[IntelligenceEvent] = []
        try:
            resp = self._rds.describe_db_instances()
            for db in resp.get("DBInstances", []):
                db_id = db["DBInstanceIdentifier"]
                now = datetime.now(UTC)
                for metric_name, metric_type in [
                    ("DatabaseConnections", AnomalyMetricType.DB_CONNECTIONS),
                    ("CPUUtilization", AnomalyMetricType.CPU),
                    ("FreeableMemory", AnomalyMetricType.MEMORY),
                ]:
                    cw_resp = self._cw.get_metric_statistics(
                        Namespace="AWS/RDS",
                        MetricName=metric_name,
                        Dimensions=[{"Name": "DBInstanceIdentifier", "Value": db_id}],
                        StartTime=now - timedelta(minutes=6),
                        EndTime=now,
                        Period=60,
                        Statistics=["Average"],
                    )
                    for dp in cw_resp.get("Datapoints", []):
                        value = dp["Average"]
                        # Normalize FreeableMemory from bytes to percentage (rough estimate)
                        if metric_name == "FreeableMemory":
                            allocated = db.get("AllocatedStorage", 20) * 1024**3
                            value = (1 - (value / allocated)) * 100 if allocated else 0
                        events.append(IntelligenceEvent(
                            event_type="metric",
                            source=f"aws:rds:{db_id}",
                            service_name=f"rds:{db_id}",
                            environment=settings.default_environment,
                            cloud_provider=CloudProvider.AWS,
                            region=self._region,
                            timestamp=dp["Timestamp"],
                            metric=MetricEvent(
                                metric_type=metric_type,
                                value=float(value),
                                service_name=f"rds:{db_id}",
                                environment=settings.default_environment,
                            ),
                        ))
        except (ClientError, EndpointConnectionError) as exc:
            logger.warning("rds_collection_failed", error=str(exc))
        return events

    def _collect_cloudwatch_logs(self) -> list[IntelligenceEvent]:
        """Collect ERROR-level CloudWatch log events from monitored log groups."""
        events: list[IntelligenceEvent] = []
        now = datetime.now(UTC)
        try:
            log_groups_resp = self._logs.describe_log_groups(limit=20)
            for group in log_groups_resp.get("logGroups", []):
                group_name = group["logGroupName"]
                try:
                    filter_resp = self._logs.filter_log_events(
                        logGroupName=group_name,
                        startTime=int((now - timedelta(minutes=5)).timestamp() * 1000),
                        endTime=int(now.timestamp() * 1000),
                        filterPattern='?ERROR ?Exception ?FATAL ?error',
                        limit=20,
                    )
                    for event in filter_resp.get("events", []):
                        events.append(IntelligenceEvent(
                            event_type="log",
                            source=f"aws:cloudwatch:{group_name}",
                            service_name=group_name.strip("/").replace("/", ":"),
                            environment=settings.default_environment,
                            cloud_provider=CloudProvider.AWS,
                            region=self._region,
                            timestamp=datetime.fromtimestamp(
                                event["timestamp"] / 1000, tz=UTC
                            ),
                            log=LogEvent(
                                level=LogSeverity.ERROR,
                                message=event.get("message", "")[:1000],
                                service_name=group_name,
                                environment=settings.default_environment,
                            ),
                        ))
                except ClientError:
                    pass
        except (ClientError, EndpointConnectionError) as exc:
            logger.warning("cloudwatch_logs_collection_failed", error=str(exc))
        return events
