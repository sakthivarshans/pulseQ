"""
training/run_simulations.py
─────────────────────────────
Dataset 6: training/data/simulation_scenarios.json
Schema:
  [
    {
      "scenario_id": "SIM-001",
      "name": "Database Overload Cascade",
      "description": "...",
      "services": ["api-gateway", "auth-service", "postgres"],
      "initial_conditions": {
        "cpu_usage_percent": 85.0,
        "memory_usage_percent": 72.0,
        "error_rate_percent": 0.12,
        "p99_latency_ms": 1200.0
      },
      "anomaly_type": "database_overload",
      "expected_alerts": ["high_latency", "high_error_rate"],
      "expected_root_cause": "database_overload",
      "remediation_step": "Kill long-running queries, restart replica, add read replicas",
      "duration_seconds": 300
    }
  ]

Runs each simulation scenario through the trained anomaly classifier
and (optionally) the IsolationForest. Verifies detection rate and
outputs a Simulation Accuracy Report.

Saves:
  models/simulation_results.json
"""
from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime

import numpy as np

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "simulation_scenarios.json")
MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
RESULTS_FILE = os.path.join(MODELS_DIR, "simulation_results.json")

FEATURE_COLS_FILE = os.path.join(MODELS_DIR, "feature_columns.json")
CLASSIFIER_FILE = os.path.join(MODELS_DIR, "anomaly_classifier.joblib")
ISOLATION_FILE = os.path.join(MODELS_DIR, "isolation_forest.joblib")


def _generate_default_scenarios() -> list[dict]:
    """Minimal built-in scenarios used when the JSON file is missing."""
    return [
        {
            "scenario_id": "SIM-001",
            "name": "CPU Spike — Payment Service",
            "anomaly_type": "cpu_spike",
            "initial_conditions": {
                "cpu_usage_percent": 94.0,
                "memory_usage_percent": 65.0,
                "error_rate_percent": 0.03,
                "p99_latency_ms": 400.0,
            },
            "expected_root_cause": "cpu_spike",
        },
        {
            "scenario_id": "SIM-002",
            "name": "Memory Leak — Notification Service",
            "anomaly_type": "memory_leak",
            "initial_conditions": {
                "cpu_usage_percent": 45.0,
                "memory_usage_percent": 97.0,
                "error_rate_percent": 0.08,
                "p99_latency_ms": 850.0,
            },
            "expected_root_cause": "memory_leak",
        },
        {
            "scenario_id": "SIM-003",
            "name": "Database Overload Cascade",
            "anomaly_type": "database_overload",
            "initial_conditions": {
                "cpu_usage_percent": 55.0,
                "memory_usage_percent": 70.0,
                "error_rate_percent": 0.22,
                "p99_latency_ms": 3500.0,
            },
            "expected_root_cause": "database_overload",
        },
        {
            "scenario_id": "SIM-004",
            "name": "Normal Operations Baseline",
            "anomaly_type": "normal",
            "initial_conditions": {
                "cpu_usage_percent": 30.0,
                "memory_usage_percent": 40.0,
                "error_rate_percent": 0.005,
                "p99_latency_ms": 120.0,
            },
            "expected_root_cause": "none",
        },
    ]


def main() -> None:
    os.makedirs(MODELS_DIR, exist_ok=True)

    # Load scenarios
    if not os.path.exists(DATA_FILE):
        print(f"[WARN] Scenarios file not found: {DATA_FILE}")
        print("       Using built-in default scenarios…")
        scenarios = _generate_default_scenarios()
    else:
        print(f"[INFO] Loading scenarios: {DATA_FILE}")
        with open(DATA_FILE) as f:
            content = f.read().strip()
        try:
            data = json.loads(content)
            scenarios = data if isinstance(data, list) else data.get("scenarios", data.get("simulation_scenarios", []))
        except json.JSONDecodeError as exc:
            print(f"[ERROR] Invalid JSON: {exc}")
            sys.exit(1)

    print(f"[INFO] Loaded {len(scenarios)} scenarios")

    # Load feature column list
    feature_cols = ["cpu_usage_percent", "memory_usage_percent", "error_rate_percent", "p99_latency_ms"]
    if os.path.exists(FEATURE_COLS_FILE):
        with open(FEATURE_COLS_FILE) as f:
            feature_cols = json.load(f)
        print(f"[INFO] Feature columns: {feature_cols}")

    # Load models
    clf = None
    iso = None
    try:
        import joblib
        if os.path.exists(CLASSIFIER_FILE):
            clf = joblib.load(CLASSIFIER_FILE)
            print(f"[OK]   Loaded anomaly classifier: {CLASSIFIER_FILE}")
        else:
            print(f"[WARN] Classifier not found: {CLASSIFIER_FILE}")
            print("       Run train_anomaly_models.py first")

        if os.path.exists(ISOLATION_FILE):
            iso = joblib.load(ISOLATION_FILE)
            print(f"[OK]   Loaded IsolationForest: {ISOLATION_FILE}")
    except ImportError:
        print("[WARN] joblib not available — running heuristic-only mode")

    # ── Simulate each scenario ────────────────────────────────────────────────
    results: list[dict] = []
    correct_detections = 0
    false_positives = 0
    false_negatives = 0

    print("\n[INFO] Running scenarios…")
    for scenario in scenarios:
        sid = scenario.get("scenario_id", "—")
        name = scenario.get("name", "Unnamed")
        conditions = scenario.get("initial_conditions", {})
        expected_is_anomaly = scenario.get("anomaly_type", "normal") != "normal"

        # Build feature vector
        feature_vec = np.array([[
            float(conditions.get(col, 0.0))
            for col in feature_cols
        ]])

        # Predictions
        clf_prediction = None
        iso_prediction = None
        heuristic_prediction = None

        if clf is not None:
            clf_prediction = bool(clf.predict(feature_vec)[0])

        if iso is not None:
            iso_score = iso.decision_function(feature_vec)[0]
            iso_prediction = iso_score < 0  # negative = anomaly

        # Simple heuristic fallback (used when models are not available)
        cpu = float(conditions.get("cpu_usage_percent", 0))
        mem = float(conditions.get("memory_usage_percent", 0))
        err = float(conditions.get("error_rate_percent", 0))
        p99 = float(conditions.get("p99_latency_ms", 0))
        heuristic_prediction = (cpu > 85 or mem > 90 or err > 0.1 or p99 > 1000)

        # Final prediction: model if available else heuristic
        final_prediction = clf_prediction if clf_prediction is not None else heuristic_prediction

        # Correctness
        is_correct = (final_prediction == expected_is_anomaly)
        if is_correct:
            correct_detections += 1
        elif final_prediction and not expected_is_anomaly:
            false_positives += 1
        elif not final_prediction and expected_is_anomaly:
            false_negatives += 1

        status = "✓ DETECTED" if (final_prediction and expected_is_anomaly) else (
            "✗ MISSED" if (not final_prediction and expected_is_anomaly) else (
                "✗ FALSE POSITIVE" if (final_prediction and not expected_is_anomaly) else "✓ NORMAL"
            )
        )
        print(f"   {sid:10s}  {name:40s}  {status}")

        results.append({
            "scenario_id": sid,
            "name": name,
            "anomaly_type": scenario.get("anomaly_type", "normal"),
            "expected_is_anomaly": bool(expected_is_anomaly),
            "predicted_is_anomaly": bool(final_prediction),
            "predicted_by": "classifier" if clf_prediction is not None else "heuristic",
            "is_correct": bool(is_correct),
            "isolation_forest_flagged": bool(iso_prediction) if iso_prediction is not None else None,
            "initial_conditions": conditions,
            "expected_root_cause": scenario.get("expected_root_cause", "unknown"),
        })

    # ── Summary ───────────────────────────────────────────────────────────────
    total = len(scenarios)
    detection_rate = correct_detections / total if total > 0 else 0.0

    print(f"\n[METRICS] Total scenarios:    {total}")
    print(f"[METRICS] Correct detections: {correct_detections}")
    print(f"[METRICS] False positives:    {false_positives}")
    print(f"[METRICS] False negatives:    {false_negatives}")
    print(f"[METRICS] Detection accuracy: {detection_rate:.1%}")

    # ── Save results ──────────────────────────────────────────────────────────
    summary = {
        "run_at": datetime.now(UTC).isoformat(),
        "total_scenarios": total,
        "correct_detections": correct_detections,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "detection_accuracy": round(detection_rate, 4),
        "models_used": {
            "anomaly_classifier": clf is not None,
            "isolation_forest": iso is not None,
        },
        "results": results,
    }
    with open(RESULTS_FILE, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n[OK]   Results saved: {RESULTS_FILE}")
    print("[DONE] SIMULATION COMPLETE")


if __name__ == "__main__":
    main()
