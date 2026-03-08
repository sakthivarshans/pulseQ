"""
training/generate_dataset.py  
──────────────────────────────
Generates synthetic training data for NeuralOps ML models.
Creates realistic normal + anomalous metric profiles per service.
Outputs CSV files with labeled rows.
"""
from __future__ import annotations

import csv
import json
import math
import os
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from shared.schemas import AnomalyMetricType

_METRICS = [m.value for m in AnomalyMetricType]


def _normal_profile(t: float, service_idx: int = 0) -> dict[str, float]:
    """Generate a realistic normal metric snapshot with daily seasonality."""
    hour_of_day = (t / 3600) % 24
    # Daily traffic pattern: low at night, high midday
    traffic_factor = 0.3 + 0.7 * abs(math.sin(math.pi * hour_of_day / 12))
    base_cpu = 25 + 20 * traffic_factor + service_idx * 5
    return {
        "cpu": max(0, min(100, base_cpu + random.gauss(0, 3))),
        "memory": max(0, min(100, 45 + 15 * traffic_factor + random.gauss(0, 2))),
        "latency": max(0, 80 + 120 * traffic_factor + random.gauss(0, 15)),
        "request_rate": max(0, 200 * traffic_factor + random.gauss(0, 20)),
        "error_rate": max(0, 0.5 + random.gauss(0, 0.2)),
        "disk_io": max(0, 15 + 10 * traffic_factor + random.gauss(0, 3)),
        "network_in": max(0, 1e6 * traffic_factor + random.gauss(0, 1e5)),
        "network_out": max(0, 8e5 * traffic_factor + random.gauss(0, 8e4)),
        "db_connections": max(0, 40 + 50 * traffic_factor + random.gauss(0, 5)),
        "queue_depth": max(0, 10 + 30 * traffic_factor + random.gauss(0, 5)),
        "gc_pause": max(0, 20 + 10 * traffic_factor + random.gauss(0, 5)),
        "thread_count": max(0, 50 + 100 * traffic_factor + random.gauss(0, 10)),
    }


def _anomaly_profile(profile: dict[str, float], anomaly_type: str) -> dict[str, float]:
    """Inject a specific anomaly pattern into a normal profile."""
    p = profile.copy()
    if anomaly_type == "cpu_spike":
        p["cpu"] = random.uniform(85, 99)
        p["latency"] *= random.uniform(2, 4)
    elif anomaly_type == "memory_leak":
        p["memory"] = random.uniform(88, 99)
        p["gc_pause"] *= random.uniform(3, 8)
        p["latency"] *= random.uniform(1.5, 3)
    elif anomaly_type == "traffic_surge":
        factor = random.uniform(3, 6)
        p["request_rate"] *= factor
        p["cpu"] = min(99, p["cpu"] * factor * 0.5)
        p["latency"] *= random.uniform(1.5, 3)
        p["db_connections"] *= random.uniform(2, 4)
    elif anomaly_type == "db_connection_exhaustion":
        p["db_connections"] = random.uniform(450, 500)
        p["latency"] *= random.uniform(5, 10)
        p["error_rate"] = random.uniform(15, 40)
    elif anomaly_type == "error_explosion":
        p["error_rate"] = random.uniform(20, 60)
        p["latency"] *= random.uniform(2, 5)
    elif anomaly_type == "network_saturation":
        p["network_in"] *= random.uniform(8, 15)
        p["network_out"] *= random.uniform(8, 15)
        p["latency"] *= random.uniform(3, 7)
    elif anomaly_type == "disk_io_bottleneck":
        p["disk_io"] = random.uniform(90, 100)
        p["latency"] *= random.uniform(4, 8)
    return p


_ANOMALY_TYPES = [
    "cpu_spike", "memory_leak", "traffic_surge",
    "db_connection_exhaustion", "error_explosion",
    "network_saturation", "disk_io_bottleneck",
]


def generate_dataset(
    output_path: str,
    n_normal: int = 5000,
    n_anomaly: int = 500,
    n_services: int = 5,
) -> None:
    """Generate labeled synthetic dataset and save as CSV."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    rows: list[dict[str, float | int]] = []
    now_epoch = datetime.now(UTC).timestamp()

    # Normal samples
    for i in range(n_normal):
        t = now_epoch - (n_normal - i) * 60  # 1-minute intervals
        svc_idx = i % n_services
        snap = _normal_profile(t, svc_idx)
        snap["is_anomaly"] = 0
        rows.append(snap)

    # Anomaly samples
    for i in range(n_anomaly):
        t = now_epoch - random.randint(0, n_normal * 60)
        svc_idx = i % n_services
        base = _normal_profile(t, svc_idx)
        atype = random.choice(_ANOMALY_TYPES)
        snap = _anomaly_profile(base, atype)
        snap["is_anomaly"] = 1
        rows.append(snap)

    # Shuffle
    random.shuffle(rows)

    fields = _METRICS + ["is_anomaly"]
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: round(row.get(k, 0.0), 4) for k in fields})

    print(f"Generated {len(rows):,} samples ({n_normal:,} normal, {n_anomaly:,} anomalous) → {output_path}")


def generate_simulation_scenarios(output_path: str) -> None:
    """Generate 12 realistic incident simulation scenarios."""
    scenarios = [
        {
            "scenario_id": "sc_cpu_spike_001",
            "name": "CPU Spike — High Traffic Surge",
            "description": "Sudden traffic spike causes CPU saturation across API services",
            "affected_services": ["api-gateway", "user-service", "payment-service"],
            "anomaly_type": "traffic_surge",
            "severity": "P2",
            "expected_rca": "Traffic surge from marketing campaign overwhelmed API Gateway",
            "expected_remediation": ["kubectl_scale", "aws_asg_scale"],
            "duration_minutes": 45,
        },
        {
            "scenario_id": "sc_memory_leak_002",
            "name": "Memory Leak — Order Service",
            "description": "Gradual memory exhaustion due to unclosed DB connections",
            "affected_services": ["order-service", "postgres"],
            "anomaly_type": "memory_leak",
            "severity": "P2",
            "expected_rca": "Memory leak in order-service due to connection pool not being released",
            "expected_remediation": ["kubectl_rollout_restart"],
            "duration_minutes": 120,
        },
        {
            "scenario_id": "sc_db_exhaust_003",
            "name": "DB Connection Exhaustion — Payment Service",
            "description": "Payment service exhausts PostgreSQL connection pool",
            "affected_services": ["payment-service", "order-service", "postgres"],
            "anomaly_type": "db_connection_exhaustion",
            "severity": "P1",
            "expected_rca": "Connection pool exhaustion in payment-service after deploy v2.3.1",
            "expected_remediation": ["kubectl_rollout_restart", "cache_flush"],
            "duration_minutes": 30,
        },
        {
            "scenario_id": "sc_error_explosion_004",
            "name": "Error Rate Explosion — Auth Service",
            "description": "Authentication service returns 5XX errors after config change",
            "affected_services": ["auth-service", "api-gateway"],
            "anomaly_type": "error_explosion",
            "severity": "P1",
            "expected_rca": "Invalid JWT secret in auth-service after secret rotation",
            "expected_remediation": ["kubectl_rollout_restart"],
            "duration_minutes": 15,
        },
        {
            "scenario_id": "sc_network_005",
            "name": "Network Saturation — Data Pipeline",
            "description": "Bulk data export job saturates network bandwidth",
            "affected_services": ["data-pipeline", "storage-service"],
            "anomaly_type": "network_saturation",
            "severity": "P3",
            "expected_rca": "Poorly throttled export job consuming all network bandwidth",
            "expected_remediation": ["webhook"],
            "duration_minutes": 60,
        },
        {
            "scenario_id": "sc_disk_io_006",
            "name": "Disk I/O Bottleneck — Logging Service",
            "description": "Log aggregator disk I/O at 100% causing service degradation",
            "affected_services": ["logging-service"],
            "anomaly_type": "disk_io_bottleneck",
            "severity": "P3",
            "expected_rca": "Log rotation not configured — disk filling up",
            "expected_remediation": ["ansible_playbook"],
            "duration_minutes": 90,
        },
        {
            "scenario_id": "sc_cascade_007",
            "name": "Cascading Failure — Checkout Flow",
            "description": "Payment timeout causes order queue buildup and UI errors",
            "affected_services": ["payment-service", "order-service", "cart-service", "frontend"],
            "anomaly_type": "error_explosion",
            "severity": "P1",
            "expected_rca": "Payment provider timeout caused queue buildup and cascading 5XX errors",
            "expected_remediation": ["slack_notification", "pagerduty_alert", "kubectl_scale"],
            "duration_minutes": 35,
        },
        {
            "scenario_id": "sc_slo_breach_008",
            "name": "SLO Error Budget Exhaustion",
            "description": "99.9% availability SLO breached due to intermittent API errors",
            "affected_services": ["api-gateway"],
            "anomaly_type": "error_explosion",
            "severity": "P2",
            "expected_rca": "Sustained 2% error rate depleted monthly error budget",
            "expected_remediation": ["kubectl_rollout_restart"],
            "duration_minutes": 200,
        },
        {
            "scenario_id": "sc_noisy_009",
            "name": "False Positive — Scheduled Job",
            "description": "Weekly batch job causes expected metric spikes; should not page",
            "affected_services": ["batch-processor"],
            "anomaly_type": "cpu_spike",
            "severity": "P4",
            "expected_rca": "Scheduled weekly batch job — expected spike pattern",
            "expected_remediation": [],
            "duration_minutes": 60,
            "is_false_positive": True,
        },
        {
            "scenario_id": "sc_deploy_regression_010",
            "name": "Deployment Regression — N+1 Query Bug",
            "description": "New release introduces N+1 query causing DB overload",
            "affected_services": ["product-service", "postgres"],
            "anomaly_type": "db_connection_exhaustion",
            "severity": "P2",
            "expected_rca": "v3.2.0 deployment introduced ORM N+1 query issue",
            "expected_remediation": ["kubectl_rollout_restart"],
            "duration_minutes": 50,
        },
        {
            "scenario_id": "sc_multi_zone_011",
            "name": "Multi-AZ Connectivity Loss",
            "description": "AWS AZ us-east-1c becomes unreachable — pods evicted",
            "affected_services": ["api-gateway", "auth-service", "order-service"],
            "anomaly_type": "network_saturation",
            "severity": "P1",
            "expected_rca": "AZ connectivity loss triggered pod eviction and service degradation",
            "expected_remediation": ["aws_asg_scale", "kubectl_scale"],
            "duration_minutes": 25,
        },
        {
            "scenario_id": "sc_oom_012",
            "name": "OOMKill — ML Inference Service",
            "description": "ML inference pod hitting OOM limit under load",
            "affected_services": ["ml-inference"],
            "anomaly_type": "memory_leak",
            "severity": "P2",
            "expected_rca": "ML inference pod OOMKilled — model cache not bounded",
            "expected_remediation": ["kubectl_scale"],
            "duration_minutes": 40,
        },
    ]

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(scenarios, f, indent=2)
    print(f"Generated {len(scenarios)} simulation scenarios → {output_path}")


if __name__ == "__main__":
    generate_dataset(
        "training/data/synthetic_dataset.csv",
        n_normal=5000,
        n_anomaly=500,
    )
    generate_dataset(
        "training/data/validation_dataset.csv",
        n_normal=1000,
        n_anomaly=100,
    )
    generate_simulation_scenarios("training/data/simulation_scenarios.json")
