"""
training/train_remediation_recommender.py
─────────────────────────────────────────────
Dataset 6: remediation_history_dataset.csv
Trains a model (or heuristic-based ranker) to recommend remediation actions.
Input: Root cause type + incident severity.
Output: Ranked list of actions (e.g., Restart Service, Revert PR, Scale Up).
"""
from __future__ import annotations

import json
import os
import pickle
import sys

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder

DATASET = os.path.join(os.path.dirname(__file__), "remediation_history_dataset.csv")
MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models")


def main() -> None:
    os.makedirs(MODELS_DIR, exist_ok=True)

    if not os.path.exists(DATASET):
        print(f"[WARN] Dataset not found: {DATASET}")
        print("       Generating synthetic remediation history...")
        _generate_synthetic_dataset()

    print("[INFO] Loading remediation history dataset...")
    df = pd.read_csv(DATASET)
    
    # Features: Root Cause + Severity
    X_raw = df[["root_cause", "severity"]].fillna("unknown")
    le_rc = LabelEncoder()
    le_sev = LabelEncoder()
    
    X = pd.DataFrame({
        "root_cause": le_rc.fit_transform(X_raw["root_cause"]),
        "severity": le_sev.fit_transform(X_raw["severity"])
    })
    
    # Target: remediation_action
    le_act = LabelEncoder()
    y = le_act.fit_transform(df["remediation_action"].fillna("none"))
    
    print("[INFO] Training Remediation Recommender...")
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X, y)
    
    # Save everything
    model_path = os.path.join(MODELS_DIR, "remediation_recommender.pkl")
    with open(model_path, "wb") as f:
        pickle.dump({
            "model": model,
            "le_rc": le_rc,
            "le_sev": le_sev,
            "le_act": le_act,
            "classes": list(le_act.classes_)
        }, f)
    print(f"[OK]   Saved: {model_path}")
    
    # Also save a mapping for direct lookup in dev mode
    mapping_path = os.path.join(MODELS_DIR, "remediation_mapping.json")
    mapping = df.groupby(["root_cause", "severity"])["remediation_action"].apply(lambda x: list(x.unique())).to_dict()
    # Convert tuple keys to strings for JSON
    clean_mapping = {f"{k[0]}|{k[1]}": v for k, v in mapping.items()}
    with open(mapping_path, "w") as f:
        json.dump(clean_mapping, f, indent=2)
    print(f"[OK]   Saved: {mapping_path}")


def _generate_synthetic_dataset() -> None:
    history = [
        {"root_cause": "memory_leak", "severity": "P1", "remediation_action": "Restart pods & check memory limits"},
        {"root_cause": "cpu_thrashing", "severity": "P1", "remediation_action": "Horizontal Pod Autoscaling (Scale out)"},
        {"root_cause": "database_lock", "severity": "P2", "remediation_action": "Kill long-running queries & optimize indexes"},
        {"root_cause": "bad_deploy", "severity": "P1", "remediation_action": "Rollback to previous stable version"},
        {"root_cause": "connectivity_issue", "severity": "P1", "remediation_action": "Check VPC peering & firewall rules"},
    ]
    rows = history * 100
    pd.DataFrame(rows).to_csv(DATASET, index=False)
    print(f"[INFO] Generated synthetic remediation history at {DATASET}")


if __name__ == "__main__":
    main()
