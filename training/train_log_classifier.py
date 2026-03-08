"""
training/train_log_classifier.py
──────────────────────────────────
Dataset 2: training/data/logs_training_dataset.csv
Columns:  log_level, message, is_anomaly_indicator, related_anomaly_type

Trains and saves:
  models/log_anomaly_classifier.joblib   — binary: is anomaly?
  models/log_type_classifier.joblib      — multiclass: anomaly type
  models/log_tfidf_vectorizer.joblib     — shared TF-IDF vectorizer
"""
from __future__ import annotations

import os
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import LabelEncoder

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "logs_training_dataset.csv")
MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models")


def _generate_synthetic_data() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    templates = {
        "ERROR": [
            ("high_error_rate", "Connection refused to database host"),
            ("memory_leak", "OutOfMemoryError: Java heap space"),
            ("cpu_spike", "Thread pool exhausted, queue full"),
        ],
        "WARN": [
            ("high_error_rate", "Retry attempt 3/3 failed"),
            ("latency_spike", "Response time exceeded threshold: 2500ms"),
            ("normal", "Circuit breaker half-open state"),
        ],
        "INFO": [
            ("normal", "Request processed successfully in 45ms"),
            ("normal", "Health check passed"),
            ("normal", "Scheduled job completed"),
        ],
    }
    rows = []
    for _ in range(5000):
        level = rng.choice(["ERROR", "WARN", "INFO"], p=[0.25, 0.30, 0.45])
        anomaly_type, message = templates[level][rng.integers(0, len(templates[level]))]
        is_anomaly = 1 if anomaly_type != "normal" else 0
        rows.append({
            "log_level": level,
            "message": message,
            "is_anomaly_indicator": is_anomaly,
            "related_anomaly_type": anomaly_type,
        })
    return pd.DataFrame(rows)


def main() -> None:
    os.makedirs(MODELS_DIR, exist_ok=True)

    if not os.path.exists(DATA_FILE):
        print(f"[WARN] Dataset not found: {DATA_FILE}")
        print("       Generating synthetic log data...")
        df = _generate_synthetic_data()
    else:
        print(f"[INFO] Loading dataset: {DATA_FILE}")
        df = pd.read_csv(DATA_FILE)

    print(f"[INFO] Loaded {len(df):,} rows — {df['is_anomaly_indicator'].sum()} anomaly logs")

    # Combine log_level + message as feature text
    df["text"] = df["log_level"].fillna("") + " " + df["message"].fillna("")

    # TF-IDF vectorizer (fit once, used for both classifiers)
    print("[INFO] Fitting TF-IDF vectorizer (max_features=5000)…")
    tfidf = TfidfVectorizer(max_features=5000, ngram_range=(1, 2), min_df=2)
    X = tfidf.fit_transform(df["text"])

    vectorizer_path = os.path.join(MODELS_DIR, "log_tfidf_vectorizer.joblib")
    joblib.dump(tfidf, vectorizer_path)
    print(f"[OK]   Saved vectorizer: {vectorizer_path}")

    # ── Binary: is anomaly? ──────────────────────────────────────────────────
    y_binary = df["is_anomaly_indicator"].astype(int).values
    X_train, X_val, y_train, y_val = train_test_split(
        X, y_binary, test_size=0.2, random_state=42, stratify=y_binary
    )
    print("\n[INFO] Training binary log anomaly classifier…")
    clf = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42)
    clf.fit(X_train, y_train)
    y_pred = clf.predict(X_val)
    print(f"[METRICS] Accuracy={accuracy_score(y_val, y_pred):.4f}  F1={f1_score(y_val, y_pred):.4f}")
    clf_path = os.path.join(MODELS_DIR, "log_anomaly_classifier.joblib")
    joblib.dump(clf, clf_path)
    print(f"[OK]   Saved: {clf_path}")

    # Print top 20 most predictive features
    feature_names = tfidf.get_feature_names_out()
    coefs = clf.coef_[0]
    top_positive = [(feature_names[i], round(coefs[i], 4)) for i in coefs.argsort()[-20:][::-1]]
    print("\n[INFO] Top 20 anomaly-correlated tokens:")
    for name, coef in top_positive:
        print(f"       {name:30s} {coef:+.4f}")

    # ── Multiclass: anomaly type ─────────────────────────────────────────────
    if "related_anomaly_type" in df.columns:
        print("\n[INFO] Training multiclass log type classifier…")
        le = LabelEncoder()
        y_type = le.fit_transform(df["related_anomaly_type"].fillna("normal"))
        X_tr, X_vl, y_tr, y_vl = train_test_split(
            X, y_type, test_size=0.2, random_state=42, stratify=y_type
        )
        type_clf = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42)
        type_clf.fit(X_tr, y_tr)
        y_type_pred = type_clf.predict(X_vl)
        print(f"[METRICS] Type F1={f1_score(y_vl, y_type_pred, average='macro'):.4f}")
        type_path = os.path.join(MODELS_DIR, "log_type_classifier.joblib")
        joblib.dump({"model": type_clf, "label_encoder": le}, type_path)
        print(f"[OK]   Saved: {type_path}")

    print("\n[DONE] ALL LOG CLASSIFIERS TRAINED SUCCESSFULLY")


if __name__ == "__main__":
    main()
