"""
training/analyze_conversations.py
───────────────────────────────────
Dataset 5: training/data/chatbot_conversations_dataset.csv
(Same CSV as evaluate_chatbot.py — different analysis target)

Analyzes conversation patterns to derive CONTEXT WEIGHTS:
  - Which context fields (active_incidents, current_metrics, repo_errors,
    similar_past_incidents) are most useful per intent
  - Which intents are most common
  - Average conversation length per intent

Outputs:
  models/chatbot_context_weights.json
  models/conversation_analysis.json
"""
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from datetime import UTC, datetime

import numpy as np
import pandas as pd

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "chatbot_conversations_dataset.csv")
MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
WEIGHTS_FILE = os.path.join(MODELS_DIR, "chatbot_context_weights.json")
ANALYSIS_FILE = os.path.join(MODELS_DIR, "conversation_analysis.json")

# Heuristic mapping: which context fields are most useful for each intent
# This will be overridden if the dataset has a 'context_retrieved' field
DEFAULT_CONTEXT_WEIGHTS: dict[str, list[str]] = {
    "error_explanation":  ["repo_errors", "current_metrics", "active_incidents"],
    "code_question":      ["repo_errors"],
    "metric_question":    ["current_metrics", "active_incidents"],
    "incident_question":  ["active_incidents", "similar_past_incidents"],
    "prediction_question":["current_metrics", "similar_past_incidents"],
    "deployment_question":["active_incidents", "repo_errors"],
    "general":            ["active_incidents", "current_metrics"],
}


def _keyword_classify(message: str) -> str:
    INTENT_KEYWORDS = {
        "error_explanation":  ["error", "exception", "failed", "crash", "500", "traceback"],
        "code_question":      ["code", "function", "file", "class", "module", "import"],
        "metric_question":    ["cpu", "memory", "latency", "requests", "p99"],
        "incident_question":  ["incident", "outage", "down", "issue", "alert"],
        "prediction_question":["predict", "will", "risk", "forecast", "trend"],
        "deployment_question":["deploy", "release", "commit", "rollback"],
    }
    lower = message.lower()
    for r, keywords in INTENT_KEYWORDS.items():
        if any(k in lower for k in keywords):
            return r
    return "general"


def main() -> None:
    os.makedirs(MODELS_DIR, exist_ok=True)

    if not os.path.exists(DATA_FILE):
        print(f"[WARN] Dataset not found: {DATA_FILE}")
        print("       Writing default context weights without data analysis.")
        with open(WEIGHTS_FILE, "w") as f:
            json.dump(DEFAULT_CONTEXT_WEIGHTS, f, indent=2)
        print(f"[OK]   Default weights written: {WEIGHTS_FILE}")
        return

    print(f"[INFO] Loading conversations: {DATA_FILE}")
    df = pd.read_csv(DATA_FILE)
    print(f"[INFO] Loaded {len(df):,} rows")

    # Use labeled intent if available, else classify
    if "intent_label" in df.columns:
        df["intent"] = df["intent_label"].fillna(df["user_message"].apply(_keyword_classify))
    elif "user_message" in df.columns:
        df["intent"] = df["user_message"].apply(_keyword_classify)
    else:
        print("[ERROR] No 'user_message' or 'intent_label' column found")
        return

    # ── Intent frequency distribution ────────────────────────────────────────
    intent_counts = df["intent"].value_counts().to_dict()
    total = len(df)
    intent_pct = {k: round(v / total, 4) for k, v in intent_counts.items()}

    print("\n[INFO] Intent distribution:")
    for intent, pct in sorted(intent_pct.items(), key=lambda x: -x[1]):
        print(f"       {intent:30s}  {intent_counts[intent]:5d} ({pct*100:5.1f}%)")

    # ── Context field analysis ────────────────────────────────────────────────
    context_weights: dict[str, list[str]] = dict(DEFAULT_CONTEXT_WEIGHTS)

    if "context_retrieved" in df.columns:
        print("\n[INFO] Analyzing which context fields correlate with high quality responses…")
        # context_retrieved expected to be a JSON string or comma-separated field names
        context_usefulness: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        quality_col = "response_quality_score" if "response_quality_score" in df.columns else None

        for _, row in df.iterrows():
            intent = row.get("intent", "general")
            ctx_raw = str(row.get("context_retrieved", ""))
            # Parse context fields — try JSON first, then comma-split
            try:
                ctx_fields = json.loads(ctx_raw).keys() if ctx_raw.startswith("{") else ctx_raw.split(",")
            except Exception:
                ctx_fields = ctx_raw.split(",")
            quality = float(row.get(quality_col, 0.5)) if quality_col else 0.5
            for field in ctx_fields:
                field = field.strip()
                if field:
                    context_usefulness[intent][field].append(quality)

        # Build context weights: fields sorted by mean quality when that field is present
        for intent, field_qualities in context_usefulness.items():
            if not field_qualities:
                continue
            ranked = sorted(
                field_qualities.items(),
                key=lambda x: np.mean(x[1]),
                reverse=True,
            )
            context_weights[intent] = [field for field, _ in ranked]

    # ── Save context weights ──────────────────────────────────────────────────
    with open(WEIGHTS_FILE, "w") as f:
        json.dump(context_weights, f, indent=2)
    print(f"\n[OK]   Context weights saved: {WEIGHTS_FILE}")

    # ── Detailed analysis report ──────────────────────────────────────────────
    analysis = {
        "analyzed_at": datetime.now(UTC).isoformat(),
        "total_conversations": total,
        "intent_distribution": {k: {"count": v, "fraction": intent_pct[k]} for k, v in intent_counts.items()},
        "context_weights": context_weights,
    }

    if "model_used" in df.columns:
        analysis["model_usage"] = df["model_used"].value_counts().to_dict()

    if "response_quality_score" in df.columns:
        scores = pd.to_numeric(df["response_quality_score"], errors="coerce").dropna()
        analysis["quality_by_intent"] = {}
        for intent in df["intent"].unique():
            mask = df["intent"] == intent
            intent_scores = pd.to_numeric(df.loc[mask, "response_quality_score"], errors="coerce").dropna()
            if len(intent_scores) > 0:
                analysis["quality_by_intent"][intent] = round(float(intent_scores.mean()), 4)

    with open(ANALYSIS_FILE, "w") as f:
        json.dump(analysis, f, indent=2)
    print(f"[OK]   Analysis report saved: {ANALYSIS_FILE}")
    print("[DONE] CONVERSATION ANALYSIS COMPLETE")


if __name__ == "__main__":
    main()
