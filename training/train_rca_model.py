"""
training/train_rca_model.py
──────────────────────────────
Dataset 5: root_cause_analysis_dataset.csv
Trains a model to link anomalous metrics and logs to specific root causes.
Input: Features from metrics + keywords from logs.
Output: Probability distribution over known root cause types (e.g., OOM, Network, Code Bug).
"""
from __future__ import annotations

import os
import pickle
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

DATASET = os.path.join(os.path.dirname(__file__), "root_cause_analysis_dataset.csv")
MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models")


def main() -> None:
    os.makedirs(MODELS_DIR, exist_ok=True)

    if not os.path.exists(DATASET):
        print(f"[WARN] Dataset not found: {DATASET}")
        print("       Generating synthetic RCA dataset...")
        _generate_synthetic_dataset()

    print("[INFO] Loading RCA dataset...")
    df = pd.read_csv(DATASET)
    
    # Simple feature engineering: metrics avg + log keyword counts
    # In production, this would be a more complex embedding
    feature_cols = [c for c in df.columns if c not in ("root_cause", "incident_id")]
    X = df[feature_cols].fillna(0)
    
    le = LabelEncoder()
    y = le.fit_transform(df["root_cause"].fillna("unknown"))
    
    X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42)
    
    print("[INFO] Training Root Cause Analysis (RCA) model...")
    model = GradientBoostingClassifier(n_estimators=100, learning_rate=0.1, max_depth=3, random_state=42)
    model.fit(X_train, y_train)
    
    y_pred = model.predict(X_val)
    print(f"[METRICS] RCA Model Precision/Recall:")
    print(classification_report(y_val, y_pred, target_names=list(le.classes_)))
    
    # Save model and label encoder
    model_path = os.path.join(MODELS_DIR, "rca_model.pkl")
    with open(model_path, "wb") as f:
        pickle.dump({
            "model": model,
            "label_encoder": le,
            "feature_cols": list(X.columns)
        }, f)
    print(f"[OK]   Saved: {model_path}")


def _generate_synthetic_dataset() -> None:
    root_causes = ["memory_leak", "cpu_thrashing", "database_lock", "connectivity_issue", "bad_deploy"]
    data = []
    for _ in range(800):
        rc = np.random.choice(root_causes)
        # Generate correlated features
        row = {
            "avg_cpu": np.random.normal(90, 5) if rc == "cpu_thrashing" else np.random.normal(40, 10),
            "avg_mem": np.random.normal(95, 2) if rc == "memory_leak" else np.random.normal(60, 15),
            "error_rate": np.random.normal(0.5, 0.1) if rc == "bad_deploy" else np.random.normal(0.01, 0.01),
            "root_cause": rc
        }
        data.append(row)
        
    pd.DataFrame(data).to_csv(DATASET, index=False)
    print(f"[INFO] Generated synthetic RCA data at {DATASET}")


if __name__ == "__main__":
    main()
