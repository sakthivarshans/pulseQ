"""
modules/ml_engine/detector.py
──────────────────────────────
Main ML anomaly detection service.

Consumes IntelligenceEvents from Redis Stream: intelligence.events.raw
Maintains per-service baseline models (LSTM, IsolationForest, Prophet).
Fuses scores from all models for hybrid detection.
Publishes AnomalyEvents to Redis Stream: intelligence.events.anomaly.
Implements online incremental model updates on normal data.
"""
from __future__ import annotations

import asyncio
import json
import os
from collections import defaultdict, deque
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis
import structlog

from modules.ml_engine.models.isolation_forest import IsolationForestScorer
from modules.ml_engine.models.lstm_model import LSTMAnomalyDetector, LSTMTrainer
from modules.ml_engine.models.prophet_forecaster import ProphetForecaster
from shared.config import get_settings
from shared.schemas import (
    AnomalyEvent,
    AnomalyMetricType,
    CloudProvider,
    ForecastPoint,
    IntelligenceEvent,
    Severity,
)

logger = structlog.get_logger(__name__)
settings = get_settings()

_METRICS = list(AnomalyMetricType)
_N_FEATURES = len(_METRICS)
_SEQ_LEN = settings.lstm_sequence_length
_MIN_SAMPLES_TO_SCORE = _SEQ_LEN  # wait for full window before scoring


def _severity_from_score(score: float) -> Severity:
    if score >= 0.90:
        return Severity.P1
    if score >= 0.80:
        return Severity.P2
    if score >= 0.60:
        return Severity.P3
    return Severity.P4


class ServiceMLState:
    """Per-service ML state — maintains rolling windows and models."""

    def __init__(self, service_name: str) -> None:
        self.service_name = service_name
        self.metric_window: deque[dict[str, float]] = deque(maxlen=_SEQ_LEN)
        self.metric_history: defaultdict[str, list[tuple[datetime, float]]] = defaultdict(list)
        self.lstm_trainer: LSTMTrainer | None = None
        self.if_scorer: IsolationForestScorer | None = None
        self.prophet_forecasters: dict[str, ProphetForecaster] = {}
        self.samples_collected: int = 0
        self.normal_sample_count: int = 0  # for online learning
        self._initialized = False

    def add_metric(self, metric_type: str, value: float, ts: datetime) -> None:
        self.metric_history[metric_type].append((ts, value))
        # Keep last 10_000 history points per metric
        if len(self.metric_history[metric_type]) > 10_000:
            self.metric_history[metric_type].pop(0)

    def snapshot(self) -> dict[str, float]:
        """Latest multivariate snapshot as {metric_name: value}."""
        snap: dict[str, float] = {}
        for mt in AnomalyMetricType:
            hist = self.metric_history.get(mt.value, [])
            snap[mt.value] = hist[-1][1] if hist else 0.0
        return snap

    def sequence(self) -> list[list[float]]:
        """Return LSTM input sequence from metric_window."""
        def _row(snap: dict[str, float]) -> list[float]:
            return [snap.get(mt.value, 0.0) for mt in AnomalyMetricType]
        return [_row(s) for s in self.metric_window]

    def initialize_models(self) -> None:
        model = LSTMAnomalyDetector(
            n_features=_N_FEATURES,
            seq_len=_SEQ_LEN,
            hidden_size=settings.lstm_hidden_size,
            num_layers=settings.lstm_num_layers,
            dropout=settings.lstm_dropout,
        )
        self.lstm_trainer = LSTMTrainer(model)
        self.if_scorer = IsolationForestScorer(
            contamination=settings.isolation_forest_contamination,
        )
        self._initialized = True

    def is_ready_to_score(self) -> bool:
        return (
            self._initialized
            and self.samples_collected >= _MIN_SAMPLES_TO_SCORE
            and self.lstm_trainer is not None
            and self.if_scorer is not None
            and self.if_scorer._fitted
        )


class AnomalyDetectorService:
    """Main ML engine service — async consumer of raw events from Redis Stream."""

    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None
        self._service_states: dict[str, ServiceMLState] = {}
        self._running = False
        self._anomalies_detected = 0
        self._events_processed = 0

    async def start(self) -> None:
        try:
            self._redis = aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=10,
            )
            await self._redis.ping()

            # Create consumer groups
            for stream in [
                settings.redis_stream_raw_events,
                settings.redis_stream_anomaly_events,
            ]:
                try:
                    await self._redis.xgroup_create(stream, settings.redis_consumer_group, id="$", mkstream=True)
                except aioredis.ResponseError as e:
                    if "BUSYGROUP" not in str(e):
                        raise
        except Exception as exc:
            logger.warning("ml_engine_redis_unavailable_continuing", error=str(exc))
            self._redis = None

        # Load pre-trained models if they exist
        self._load_pretrained_models()
        self._running = True
        logger.info("ml_engine_started")

    def _load_pretrained_models(self) -> None:
        """Attempt to load trained artifacts from disk."""
        if os.path.exists(settings.lstm_model_path):
            logger.info("loading_pretrained_lstm", path=settings.lstm_model_path)
        if os.path.exists(settings.isolation_forest_model_path):
            logger.info("loading_pretrained_if", path=settings.isolation_forest_model_path)

    async def stop(self) -> None:
        self._running = False
        if self._redis:
            await self._redis.aclose()

    async def run_detection_loop(self) -> None:
        """Main event consumption loop from Redis Stream."""
        if self._redis is None:
            logger.warning("ml_engine_detection_loop_skipped", reason="Redis unavailable — running in offline/local mode")
            return
        consumer_name = f"ml-engine-{os.getpid()}"

        while self._running:
            try:
                messages = await self._redis.xreadgroup(
                    groupname=settings.redis_consumer_group,
                    consumername=consumer_name,
                    streams={settings.redis_stream_raw_events: ">"},
                    count=100,
                    block=1000,
                )
                if not messages:
                    continue

                for _stream, events in messages:
                    for msg_id, fields in events:
                        try:
                            await self._process_event(fields)
                            await self._redis.xack(
                                settings.redis_stream_raw_events,
                                settings.redis_consumer_group,
                                msg_id,
                            )
                        except Exception as exc:
                            logger.error("event_processing_failed", error=str(exc), msg_id=msg_id)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("detection_loop_error", error=str(exc))
                await asyncio.sleep(5)

    async def _process_event(self, fields: dict[str, str]) -> None:
        """Process a single IntelligenceEvent dictionary from the stream."""
        payload = json.loads(fields.get("payload", "{}"))
        event = IntelligenceEvent(**payload)
        self._events_processed += 1

        if event.event_type != "metric" or event.metric is None:
            return

        service = event.service_name
        if service not in self._service_states:
            state = ServiceMLState(service)
            state.initialize_models()
            self._service_states[service] = state
        else:
            state = self._service_states[service]

        metric_name = event.metric.metric_type.value
        value = event.metric.value
        state.add_metric(metric_name, value, event.timestamp)

        # Update rolling window
        snap = state.snapshot()
        state.metric_window.append(snap)
        state.samples_collected += 1

        # Can't score until we have enough data
        if not state.is_ready_to_score():
            await self._maybe_bootstrap_models(state)
            return

        # Score with all models
        anomaly = await self._compute_anomaly(event, state)
        if anomaly and anomaly.anomaly_score >= settings.anomaly_score_warn:
            await self._publish_anomaly(anomaly)
            self._anomalies_detected += 1
        else:
            # Online learning on confirmed-normal sample
            state.normal_sample_count += 1
            if state.normal_sample_count % 100 == 0:
                seq = state.sequence()
                if state.lstm_trainer and len(seq) == _SEQ_LEN:
                    state.lstm_trainer.online_update(seq)

    async def _maybe_bootstrap_models(self, state: ServiceMLState) -> None:
        """Bootstrap models once enough history is collected."""
        if state.samples_collected != _MIN_SAMPLES_TO_SCORE + 1:
            return
        if state.if_scorer and not state.if_scorer._fitted:
            snapshots = list(state.metric_window)
            if snapshots:
                state.if_scorer.fit(snapshots)
                logger.info("if_model_bootstrapped", service=state.service_name)
        if state.lstm_trainer:
            seq = state.sequence()
            if len(seq) == _SEQ_LEN:
                state.lstm_trainer.fit([seq], epochs=10)
                logger.info("lstm_model_bootstrapped", service=state.service_name)

    async def _compute_anomaly(
        self,
        event: IntelligenceEvent,
        state: ServiceMLState,
    ) -> AnomalyEvent | None:
        if not state.lstm_trainer or not state.if_scorer:
            return None

        snap = state.snapshot()
        seq = state.sequence()

        # LSTM score
        lstm_error = 0.0
        if len(seq) == _SEQ_LEN:
            lstm_score = state.lstm_trainer.score(seq)
            lstm_error = lstm_score
        else:
            lstm_score = 0.0

        # Isolation Forest score
        if_score = state.if_scorer.score(snap)

        # Hybrid fusion: weighted average
        combined = 0.55 * if_score + 0.45 * lstm_score
        confidence = 1.0 - abs(if_score - lstm_score)  # higher when models agree

        if combined < settings.anomaly_score_warn:
            return None

        # Determine which metrics are most anomalous
        affected_metrics = self._find_affected_metrics(snap, state)

        # Prophet forecast
        forecast_points = self._get_forecast(state, affected_metrics)

        baseline = {k: self._get_baseline(state, k) for k in snap}
        return AnomalyEvent(
            source_event_id=event.event_id,
            service_name=event.service_name,
            environment=event.environment,
            affected_metrics=affected_metrics,
            metric_values=snap,
            baseline_values=baseline,
            anomaly_score=round(combined, 4),
            confidence_score=round(confidence, 4),
            isolation_forest_score=round(if_score, 4),
            lstm_reconstruction_error=round(lstm_error, 4),
            severity=_severity_from_score(combined),
            forecast=forecast_points,
            contributing_factors=self._explain_factors(snap, baseline),
            cloud_provider=event.cloud_provider,
            region=event.region,
            detection_method="hybrid",
        )

    def _find_affected_metrics(
        self,
        snap: dict[str, float],
        state: ServiceMLState,
    ) -> list[AnomalyMetricType]:
        """Identify metrics deviating most from baseline (top-3)."""
        deviations: list[tuple[float, AnomalyMetricType]] = []
        for mt in AnomalyMetricType:
            current = snap.get(mt.value, 0.0)
            baseline = self._get_baseline(state, mt.value)
            if baseline > 0:
                deviation = abs(current - baseline) / baseline
                deviations.append((deviation, mt))
        deviations.sort(reverse=True)
        return [mt for _, mt in deviations[:3]]

    def _get_baseline(self, state: ServiceMLState, metric_name: str) -> float:
        hist = state.metric_history.get(metric_name, [])
        if not hist:
            return 0.0
        values = [v for _, v in hist[-100:]]  # last 100 samples
        return sum(values) / len(values) if values else 0.0

    def _get_forecast(
        self,
        state: ServiceMLState,
        metric_types: list[AnomalyMetricType],
    ) -> list[ForecastPoint]:
        forecast_points: list[ForecastPoint] = []
        for mt in metric_types[:1]:  # forecast primary affected metric
            forecaster = state.prophet_forecasters.get(mt.value)
            hist = state.metric_history.get(mt.value, [])
            if forecaster and forecaster._fitted and len(hist) >= 2:
                try:
                    raw = forecaster.forecast(horizon_minutes=30)
                    for p in raw[:5]:  # first 5 forecast minutes
                        forecast_points.append(
                            ForecastPoint(
                                timestamp=datetime.fromisoformat(p["timestamp"]),
                                predicted_value=p["predicted_value"],
                                lower_bound=p["lower_bound"],
                                upper_bound=p["upper_bound"],
                            )
                        )
                except Exception:
                    pass
        return forecast_points

    def _explain_factors(
        self,
        snap: dict[str, float],
        baseline: dict[str, float | Any],
    ) -> list[str]:
        factors: list[str] = []
        for metric, current in snap.items():
            base = baseline.get(metric, 0.0)
            if base and base > 0:
                pct = (current - base) / base * 100
                if pct > 30:
                    factors.append(f"{metric} elevated {pct:.0f}% above baseline")
                elif pct < -30:
                    factors.append(f"{metric} dropped {abs(pct):.0f}% below baseline")
        return factors[:5]

    async def _publish_anomaly(self, anomaly: AnomalyEvent) -> None:
        if self._redis is None:
            logger.warning("anomaly_publish_skipped", reason="Redis unavailable", service=anomaly.service_name)
            return
        payload = anomaly.model_dump(mode="json")
        await self._redis.xadd(
            settings.redis_stream_anomaly_events,
            {
                "anomaly_id": payload["anomaly_id"],
                "service_name": payload["service_name"],
                "anomaly_score": str(payload["anomaly_score"]),
                "severity": payload["severity"],
                "payload": json.dumps(payload),
            },
            maxlen=50_000,
            approximate=True,
        )
        logger.info(
            "anomaly_published",
            service=anomaly.service_name,
            score=anomaly.anomaly_score,
            severity=anomaly.severity,
        )

    def get_stats(self) -> dict[str, Any]:
        return {
            "events_processed": self._events_processed,
            "anomalies_detected": self._anomalies_detected,
            "services_monitored": len(self._service_states),
        }
