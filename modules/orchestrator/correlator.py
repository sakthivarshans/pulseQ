"""
modules/orchestrator/correlator.py
────────────────────────────────────
Incident correlation engine.

Groups related AnomalyEvents into Incidents by:
  1. Time-window proximity (anomalies within N minutes)
  2. Service dependency graph traversal
  3. Metric pattern similarity

Calculates blast radius by traversing service dependency graph.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from shared.schemas import AnomalyEvent, BlastRadius, Incident, Severity

logger = structlog.get_logger(__name__)

# Group anomalies within this window into the same incident
CORRELATION_WINDOW_MINUTES = 10


class ServiceDependencyGraph:
    """
    In-memory directed graph of service dependencies.
    Loaded from topology cache in Redis.
    """

    def __init__(self) -> None:
        self._graph: dict[str, list[str]] = defaultdict(list)  # service -> downstream services
        self._reverse: dict[str, list[str]] = defaultdict(list)  # service -> upstream services

    def add_dependency(self, upstream: str, downstream: str) -> None:
        self._graph[upstream].append(downstream)
        self._reverse[downstream].append(upstream)

    def load_from_dict(self, topology: dict[str, dict[str, Any]]) -> None:
        for service, info in topology.items():
            for downstream in info.get("downstream_services", []):
                self.add_dependency(service, downstream)

    def get_blast_radius(
        self,
        affected_services: list[str],
        max_depth: int = 3,
    ) -> BlastRadius:
        """
        BFS through dependency graph to find all transitively affected services.
        Returns BlastRadius object with direct + at-risk service lists.
        """
        at_risk: set[str] = set()
        visited: set[str] = set(affected_services)
        queue = list(affected_services)

        for _ in range(max_depth):
            next_level: list[str] = []
            for svc in queue:
                for downstream in self._graph.get(svc, []):
                    if downstream not in visited:
                        visited.add(downstream)
                        at_risk.add(downstream)
                        next_level.append(downstream)
            queue = next_level
            if not queue:
                break

        return BlastRadius(
            directly_affected_services=list(affected_services),
            at_risk_services=list(at_risk),
            total_services_impacted=len(affected_services) + len(at_risk),
            slo_breached=False,
        )


class AnomalyCorrelator:
    """
    Groups anomalies into incidents using time-window correlation.
    Maintains open anomaly windows per service cluster.
    """

    def __init__(self, graph: ServiceDependencyGraph) -> None:
        self._graph = graph
        # Active correlation windows: cluster_key -> list of anomalies
        self._windows: dict[str, list[AnomalyEvent]] = defaultdict(list)
        self._window_opened_at: dict[str, datetime] = {}

    def _cluster_key(self, anomaly: AnomalyEvent) -> str:
        """
        Determine the correlation cluster for an anomaly.
        Uses "primary service" or groups by environment + cloud_provider.
        """
        # Find the root-most service in the dependency chain
        upstreams = self._graph._reverse.get(anomaly.service_name, [])
        if upstreams:
            # Group with the upstream root service
            return f"{anomaly.environment}:{upstreams[0]}"
        return f"{anomaly.environment}:{anomaly.service_name}"

    def add_anomaly(
        self,
        anomaly: AnomalyEvent,
    ) -> tuple[bool, str]:
        """
        Add an anomaly to the correlation engine.
        Returns (is_new_cluster, cluster_key).
        """
        key = self._cluster_key(anomaly)
        now = anomaly.detected_at
        window_open = self._window_opened_at.get(key)

        if window_open is None or (now - window_open) > timedelta(minutes=CORRELATION_WINDOW_MINUTES):
            # New cluster
            self._windows[key] = [anomaly]
            self._window_opened_at[key] = now
            return True, key

        self._windows[key].append(anomaly)
        return False, key

    def flush_window(self, cluster_key: str) -> list[AnomalyEvent]:
        """Return all anomalies in a window and clear it."""
        anomalies = self._windows.pop(cluster_key, [])
        self._window_opened_at.pop(cluster_key, None)
        return anomalies

    def build_incident(
        self,
        cluster_key: str,
        anomalies: list[AnomalyEvent],
    ) -> Incident:
        """Build an Incident from a correlated set of AnomalyEvents."""
        if not anomalies:
            raise ValueError("Cannot build incident from empty anomaly set")

        # Determine primary service (highest anomaly score)
        primary = max(anomalies, key=lambda a: a.anomaly_score)
        all_services = list({a.service_name for a in anomalies})
        peak_score = max(a.anomaly_score for a in anomalies)
        avg_confidence = sum(a.confidence_score for a in anomalies) / len(anomalies)

        # Blast radius
        blast = self._graph.get_blast_radius(all_services)

        # Determine severity — use highest of any individual anomaly
        severities = [a.severity for a in anomalies]
        severity_order = {Severity.P1: 0, Severity.P2: 1, Severity.P3: 2, Severity.P4: 3}
        final_severity = min(severities, key=lambda s: severity_order[s])

        # Title
        metric_names = [m.value for a in anomalies for m in a.affected_metrics]
        unique_metrics = list(dict.fromkeys(metric_names))[:3]
        metrics_str = ", ".join(unique_metrics)
        title = f"{primary.service_name}: anomaly detected in {metrics_str}"

        return Incident(
            title=title,
            severity=final_severity,
            primary_service=primary.service_name,
            affected_services=all_services,
            blast_radius=blast,
            environment=primary.environment,
            cloud_provider=primary.cloud_provider,
            region=primary.region,
            correlated_anomaly_ids=[a.anomaly_id for a in anomalies],
            peak_anomaly_score=round(peak_score, 4),
            ml_confidence=round(avg_confidence, 4),
            detected_at=min(a.detected_at for a in anomalies),
        )
