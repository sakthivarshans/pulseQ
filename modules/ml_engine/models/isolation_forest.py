"""
modules/ml_engine/models/isolation_forest.py
─────────────────────────────────────────────
Isolation Forest scorer for multivariate anomaly detection.
Detects point anomalies across multiple metrics simultaneously.
"""
from __future__ import annotations

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler


class IsolationForestScorer:
    """
    Wraps sklearn IsolationForest with StandardScaler preprocessing.
    Trained on multivariate metric snapshots (one row per observation).
    """

    def __init__(self, contamination: float = 0.05, n_estimators: int = 200) -> None:
        self._scaler = StandardScaler()
        self._model = IsolationForest(
            n_estimators=n_estimators,
            contamination=contamination,
            random_state=42,
            n_jobs=-1,
        )
        self._fitted = False
        self._feature_names: list[str] = []

    def fit(self, data: list[dict[str, float]]) -> dict[str, float]:
        """
        Train on a list of metric snapshots.
        Each dict maps metric name → value.
        Returns training statistics.
        """
        if not data:
            raise ValueError("Training data cannot be empty")

        self._feature_names = sorted(data[0].keys())
        X = np.array(
            [[row.get(feat, 0.0) for feat in self._feature_names] for row in data],
            dtype=np.float64,
        )
        X_scaled = self._scaler.fit_transform(X)
        self._model.fit(X_scaled)
        self._fitted = True

        # Compute scores on training data for diagnostics
        raw_scores = self._model.score_samples(X_scaled)
        return {
            "n_samples": float(len(data)),
            "n_features": float(len(self._feature_names)),
            "mean_score": float(np.mean(raw_scores)),
            "min_score": float(np.min(raw_scores)),
        }

    def score(self, snapshot: dict[str, float]) -> float:
        """
        Score a single metric snapshot.
        Returns normalized anomaly score [0, 1].
        0 = normal, 1 = highly anomalous.
        """
        if not self._fitted:
            raise RuntimeError("Model must be fitted before scoring")

        row = np.array(
            [[snapshot.get(feat, 0.0) for feat in self._feature_names]],
            dtype=np.float64,
        )
        row_scaled = self._scaler.transform(row)
        # score_samples returns negative values — more negative = more anomalous
        raw = self._model.score_samples(row_scaled)[0]
        # Normalize: typical range is [-0.7, 0] for IF with contamination=0.05
        normalized = max(0.0, min(1.0, (-raw) / 0.7))
        return float(normalized)

    def predict_batch(self, snapshots: list[dict[str, float]]) -> list[float]:
        """Score a batch of snapshots. Returns list of anomaly scores."""
        if not self._fitted:
            raise RuntimeError("Model must be fitted before scoring")
        X = np.array(
            [[row.get(feat, 0.0) for feat in self._feature_names] for row in snapshots],
            dtype=np.float64,
        )
        X_scaled = self._scaler.transform(X)
        raw_scores = self._model.score_samples(X_scaled)
        return [float(max(0.0, min(1.0, (-s) / 0.7))) for s in raw_scores]

    def save(self, path: str) -> None:
        joblib.dump(
            {
                "model": self._model,
                "scaler": self._scaler,
                "feature_names": self._feature_names,
            },
            path,
        )

    @classmethod
    def load(cls, path: str) -> "IsolationForestScorer":
        data = joblib.load(path)
        instance = cls()
        instance._model = data["model"]
        instance._scaler = data["scaler"]
        instance._feature_names = data["feature_names"]
        instance._fitted = True
        return instance
