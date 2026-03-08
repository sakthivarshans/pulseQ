"""
training/train_incident_classifier.py
──────────────────────────────────────
Dataset 4: incident_reports_dataset.csv
Trains an XGBOOST/RandomForest model to classify incident severity and impact.
Used to automatically triage new incidents based on title, description, and affected services.
"""
from __future__ import annotations

import os
import pickle
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import f1_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

DATASET = os.path.join(os.path.dirname(__file__), "incident_reports_dataset.csv")
MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models")


def main() -> None:
    os.makedirs(MODELS_DIR, exist_ok=True)

    if not os.path.exists(DATASET):
        print(f"[WARN] Dataset not found: {DATASET}")
        print("       Generating synthetic incident reports...")
        _generate_synthetic_dataset()

    print("[INFO] Loading incident report dataset...")
    df = pd.read_csv(DATASET)
    
    # Features: Title + Description
    df["full_text"] = df["title"].fillna("") + " " + df["description"].fillna("")
    
    # ── Text Vectorizer ─────────────────────────────────────────────────────────
    tfidf = TfidfVectorizer(max_features=5000, stop_words="english")
    X_text = tfidf.fit_transform(df["full_text"])
    
    # ── Labels: Severity (P1-P4) ───────────────────────────────────────────────
    le = LabelEncoder()
    y = le.fit_transform(df["severity"].fillna("P3"))
    
    X_train, X_val, y_train, y_val = train_test_split(X_text, y, test_size=0.2, random_state=42)
    
    print("[INFO] Training incident severity classifier...")
    model = RandomForestClassifier(n_estimators=100, class_weight="balanced", random_state=42)
    model.fit(X_train, y_train)
    
    y_pred = model.predict(X_val)
    print(f"[METRICS] Incident Severity F1={f1_score(y_val, y_pred, average='macro'):.4f}")
    
    # Save model, vectorizer, and label encoder
    model_path = os.path.join(MODELS_DIR, "incident_classifier.pkl")
    with open(model_path, "wb") as f:
        pickle.dump({
            "model": model,
            "tfidf": tfidf,
            "label_encoder": le,
            "target_names": list(le.classes_)
        }, f)
    print(f"[OK]   Saved: {model_path}")


def _generate_synthetic_dataset() -> None:
    severities = ["P1", "P2", "P3", "P4"]
    data = []
    for _ in range(1000):
        sev = np.random.choice(severities, p=[0.1, 0.2, 0.4, 0.3])
        if sev == "P1":
            title = "Site is DOWN"
            desc = "Entire production cluster is unresponsive. All health checks failing."
        elif sev == "P2":
            title = "Checkout is slow"
            desc = "Users reporting 10s latency during checkout process."
        else:
            title = "Minor UI bug"
            desc = "Button color is incorrect on mobile view."
            
        data.append({"title": title, "description": desc, "severity": sev})
        
    pd.DataFrame(data).to_csv(DATASET, index=False)
    print(f"[INFO] Generated synthetic incidents at {DATASET}")


if __name__ == "__main__":
    main()
