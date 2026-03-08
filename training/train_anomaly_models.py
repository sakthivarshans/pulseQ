"""
training/train_anomaly_models.py
─────────────────────────────────
Dataset 1: training/data/metrics_training_dataset.csv
Columns:  timestamp, service_name, cpu_usage_percent, memory_usage_percent,
          error_rate_percent, p99_latency_ms, is_anomaly, anomaly_type,
          anomaly_severity, root_cause_category

Trains and saves:
  models/isolation_forest.joblib         — unsupervised anomaly detector
  models/anomaly_classifier.joblib       — binary classifier (is_anomaly)
  models/anomaly_type_classifier.joblib  — multiclass (anomaly_type)
  models/feature_columns.json            — ordered list of feature columns
"""
from __future__ import annotations

import json
import os
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "metrics_training_dataset.csv")
MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models")

FEATURE_COLS = [
    "cpu_usage_percent",
    "memory_usage_percent",
    "error_rate_percent",
    "p99_latency_ms",
]


def _generate_synthetic_data() -> pd.DataFrame:
    """Generate realistic-looking synthetic metrics data (used when CSV is missing)."""
    rng = np.random.default_rng(42)
    n = 10_000
    rows = []
    for _ in range(n):
        is_anomaly = int(rng.random() < 0.15)
        if is_anomaly:
            cpu = float(rng.uniform(80, 100))
            mem = float(rng.uniform(75, 100))
            err = float(rng.uniform(0.05, 0.30))
            p99 = float(rng.uniform(500, 5000))
            anomaly_type = rng.choice(["cpu_spike", "memory_leak", "high_error_rate", "latency_spike"])
            severity = rng.choice(["critical", "high", "medium"])
        else:
            cpu = float(rng.uniform(10, 70))
            mem = float(rng.uniform(20, 65))
            err = float(rng.uniform(0.0, 0.02))
            p99 = float(rng.uniform(50, 300))
            anomaly_type = "normal"
            severity = "none"
        rows.append({
            "cpu_usage_percent": cpu,
            "memory_usage_percent": mem,
            "error_rate_percent": err,
            "p99_latency_ms": p99,
            "is_anomaly": is_anomaly,
            "anomaly_type": anomaly_type,
            "anomaly_severity": severity,
        })
    return pd.DataFrame(rows)


def main() -> None:
    os.makedirs(MODELS_DIR, exist_ok=True)

    if not os.path.exists(DATA_FILE):
        print(f"[WARN] Dataset not found: {DATA_FILE}")
        print("       Generating synthetic data...")
        df = _generate_synthetic_data()
    else:
        print(f"[INFO] Loading dataset: {DATA_FILE}")
        df = pd.read_csv(DATA_FILE)

    print(f"[INFO] Loaded {len(df):,} rows — {df['is_anomaly'].sum()} anomalies")

    # Only keep columns that exist in the dataset
    available_features = [c for c in FEATURE_COLS if c in df.columns]
    if not available_features:
        print("[ERROR] None of the expected feature columns found in dataset.")
        sys.exit(1)

    # Save the exact feature column list for inference
    feature_path = os.path.join(MODELS_DIR, "feature_columns.json")
    with open(feature_path, "w") as f:
        json.dump(available_features, f)
    print(f"[INFO] Saved feature column list: {available_features}")

    X = df[available_features].fillna(0).values
    y_binary = df["is_anomaly"].astype(int).values

    # Split by time order (not random) to prevent data leakage
    split = int(len(df) * 0.8)
    X_train, X_val = X[:split], X[split:]
    y_train, y_val = y_binary[:split], y_binary[split:]

    # ── Model 1: IsolationForest (trained on NORMAL samples only) ─────────────
    normal_mask = y_train == 0
    X_normal = X_train[normal_mask]
    print(f"\n[INFO] Training IsolationForest on {len(X_normal):,} normal samples…")
    iso = IsolationForest(n_estimators=200, contamination=0.15, random_state=42)
    iso.fit(X_normal)
    iso_path = os.path.join(MODELS_DIR, "isolation_forest.joblib")
    joblib.dump(iso, iso_path)
    print(f"[OK]   Saved: {iso_path}")

    # ── Model 2: Binary anomaly classifier ────────────────────────────────────
    print(f"\n[INFO] Training binary anomaly classifier…")
    clf = RandomForestClassifier(
        n_estimators=200, class_weight="balanced", random_state=42, n_jobs=-1
    )
    clf.fit(X_train, y_train)
    y_pred = clf.predict(X_val)
    print(f"[METRICS] Binary Classifier — F1={f1_score(y_val, y_pred, average='macro'):.4f}")
    print(classification_report(y_val, y_pred, target_names=["normal", "anomaly"]))
    clf_path = os.path.join(MODELS_DIR, "anomaly_classifier.joblib")
    joblib.dump(clf, clf_path)
    print(f"[OK]   Saved: {clf_path}")

    # ── Model 3: Multiclass anomaly type classifier ───────────────────────────
    if "anomaly_type" in df.columns:
        print(f"\n[INFO] Training multiclass anomaly type classifier…")
        le = LabelEncoder()
        y_type = le.fit_transform(df["anomaly_type"].fillna("normal"))
        y_type_train, y_type_val = y_type[:split], y_type[split:]
        type_clf = RandomForestClassifier(
            n_estimators=200, class_weight="balanced", random_state=42, n_jobs=-1
        )
        type_clf.fit(X_train, y_type_train)
        y_type_pred = type_clf.predict(X_val)
        print(f"[METRICS] Type Classifier — F1={f1_score(y_type_val, y_type_pred, average='macro'):.4f}")
        type_path = os.path.join(MODELS_DIR, "anomaly_type_classifier.joblib")
        joblib.dump({"model": type_clf, "label_encoder": le}, type_path)
        print(f"[OK]   Saved: {type_path}")

    print("\n[DONE] ALL ANOMALY MODELS TRAINED SUCCESSFULLY")


if __name__ == "__main__":
    main()
