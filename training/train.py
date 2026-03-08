"""
training/train.py
──────────────────
Model training script for NeuralOps.
Trains LSTM autoencoder and Isolation Forest on synthetic + real telemetry data.
Saves versioned model artifacts to configured paths.
Run: python -m training.train --epochs 200 --min-samples 1000
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import structlog

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.ml_engine.models.isolation_forest import IsolationForestScorer
from modules.ml_engine.models.lstm_model import LSTMAnomalyDetector, LSTMTrainer
from modules.ml_engine.models.prophet_forecaster import ProphetForecaster
from shared.config import get_settings
from shared.schemas import AnomalyMetricType

logger = structlog.get_logger(__name__)
settings = get_settings()

_METRICS = [m.value for m in AnomalyMetricType]
_N_FEATURES = len(_METRICS)


def load_synthetic_dataset(path: str) -> tuple[list[dict[str, float]], list[int]]:
    """Load CSV dataset returning (rows, labels) where label=1 is anomaly."""
    rows: list[dict[str, float]] = []
    labels: list[int] = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            label = int(row.pop("is_anomaly", 0))
            rows.append({k: float(v) for k, v in row.items() if k in _METRICS})
            labels.append(label)
    logger.info("dataset_loaded", path=path, samples=len(rows), anomalies=sum(labels))
    return rows, labels


def build_lstm_sequences(
    rows: list[dict[str, float]], seq_len: int
) -> list[list[list[float]]]:
    """Build overlapping sliding windows for LSTM training."""
    sequences: list[list[list[float]]] = []
    for i in range(len(rows) - seq_len):
        window = rows[i : i + seq_len]
        sequences.append([[snap.get(m, 0.0) for m in _METRICS] for snap in window])
    return sequences


def evaluate_model(
    scorer: IsolationForestScorer,
    rows: list[dict[str, float]],
    labels: list[int],
) -> dict[str, float]:
    """Compute precision, recall, F1, FPR for IF scorer."""
    scores = scorer.predict_batch(rows)
    threshold = settings.anomaly_score_warn
    preds = [1 if s >= threshold else 0 for s in scores]
    tp = sum(1 for p, l in zip(preds, labels) if p == 1 and l == 1)
    fp = sum(1 for p, l in zip(preds, labels) if p == 1 and l == 0)
    tn = sum(1 for p, l in zip(preds, labels) if p == 0 and l == 0)
    fn = sum(1 for p, l in zip(preds, labels) if p == 0 and l == 1)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "fpr": fpr, "tp": tp, "fp": fp, "fn": fn}


def main(args: argparse.Namespace) -> None:
    dataset_path = args.dataset or "training/data/synthetic_dataset.csv"
    if not os.path.exists(dataset_path):
        logger.error("dataset_not_found", path=dataset_path)
        logger.info("generating_synthetic_dataset")
        from training.generate_dataset import generate_dataset
        generate_dataset(dataset_path, n_normal=args.min_samples, n_anomaly=args.min_samples // 10)

    rows, labels = load_synthetic_dataset(dataset_path)
    normal_rows = [r for r, l in zip(rows, labels) if l == 0]
    if len(normal_rows) < args.min_samples:
        logger.warning("insufficient_normal_samples", have=len(normal_rows), need=args.min_samples)

    # 1. Train Isolation Forest on normal data
    logger.info("training_isolation_forest")
    if_scorer = IsolationForestScorer(contamination=settings.isolation_forest_contamination)
    if_stats = if_scorer.fit(normal_rows)
    if_scorer.save(settings.isolation_forest_model_path)
    logger.info("isolation_forest_trained", stats=if_stats)

    # 2. Evaluate IF
    if_metrics = evaluate_model(if_scorer, rows, labels)
    logger.info("isolation_forest_evaluation", metrics=if_metrics)

    # 3. Train LSTM autoencoder on normal sequences
    logger.info("training_lstm", epochs=args.epochs)
    sequences = build_lstm_sequences(normal_rows, settings.lstm_sequence_length)
    if len(sequences) < 10:
        logger.error("insufficient_sequences", count=len(sequences))
        return
    model = LSTMAnomalyDetector(
        n_features=_N_FEATURES,
        seq_len=settings.lstm_sequence_length,
        hidden_size=settings.lstm_hidden_size,
        num_layers=settings.lstm_num_layers,
        dropout=settings.lstm_dropout,
    )
    trainer = LSTMTrainer(model)
    lstm_stats = trainer.fit(sequences, epochs=args.epochs, batch_size=64)
    trainer.save(settings.lstm_model_path)
    logger.info("lstm_trained", stats=lstm_stats)

    # 4. Save training metadata
    metadata = {
        "trained_at": datetime.now(UTC).isoformat(),
        "dataset": dataset_path,
        "n_samples": len(rows),
        "n_normal": len(normal_rows),
        "n_anomaly": sum(labels),
        "isolation_forest": {**if_stats, **if_metrics},
        "lstm": lstm_stats,
        "settings": {
            "seq_len": settings.lstm_sequence_length,
            "hidden_size": settings.lstm_hidden_size,
            "anomaly_score_warn": settings.anomaly_score_warn,
        },
    }
    meta_path = os.path.join(os.path.dirname(settings.lstm_model_path), "model_metadata.json")
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)
    logger.info("training_complete", metadata_path=meta_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NeuralOps Model Training")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--min-samples", type=int, default=1000, dest="min_samples")
    parser.add_argument("--dataset", type=str, default=None)
    main(parser.parse_args())
