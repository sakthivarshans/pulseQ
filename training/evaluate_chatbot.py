"""
training/evaluate_chatbot.py
──────────────────────────────
Dataset 4: training/data/chatbot_conversations_dataset.csv
Columns:  conversation_id, user_message, expected_response, actual_response,
          response_quality_score, context_retrieved, intent_label,
          model_used, timestamp

Evaluates chatbot quality metrics:
  - BLEU and ROUGE scores (lexical overlap)
  - Semantic similarity using sentence-transformers
  - Intent classification accuracy
  - Response quality scoring distribution
  - Per-intent breakdown
  - Confusion matrix for intent prediction

Outputs results to models/chatbot_evaluation_results.json
"""
from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime

import numpy as np
import pandas as pd

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "chatbot_conversations_dataset.csv")
MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
RESULTS_FILE = os.path.join(MODELS_DIR, "chatbot_evaluation_results.json")


# Keyword-based intent classifier (mirrors what the chatbot router does)
INTENT_KEYWORDS = {
    "error_explanation":  ["error", "exception", "failed", "crash", "500", "traceback"],
    "code_question":      ["code", "function", "file", "class", "module", "import"],
    "metric_question":    ["cpu", "memory", "latency", "requests", "p99"],
    "incident_question":  ["incident", "outage", "down", "issue", "alert"],
    "prediction_question":["predict", "will", "risk", "forecast", "trend"],
    "deployment_question":["deploy", "release", "commit", "rollback"],
}

def classify_intent(message: str) -> str:
    lower = message.lower()
    for intent, keywords in INTENT_KEYWORDS.items():
        if any(k in lower for k in keywords):
            return intent
    return "general"


def _compute_simple_bleu(reference: str, hypothesis: str) -> float:
    """Compute a simple unigram BLEU score (no NLTK required)."""
    ref_tokens = reference.lower().split()
    hyp_tokens = hypothesis.lower().split()
    if not hyp_tokens:
        return 0.0
    ref_set = set(ref_tokens)
    matches = sum(1 for t in hyp_tokens if t in ref_set)
    precision = matches / len(hyp_tokens)
    bp = min(1.0, len(hyp_tokens) / max(len(ref_tokens), 1))
    return round(bp * precision, 4)


def _compute_simple_rouge1(reference: str, hypothesis: str) -> float:
    """Compute simple unigram ROUGE-1 F1."""
    ref_tokens = set(reference.lower().split())
    hyp_tokens = set(hypothesis.lower().split())
    if not ref_tokens:
        return 0.0
    overlap = ref_tokens & hyp_tokens
    precision = len(overlap) / max(len(hyp_tokens), 1)
    recall = len(overlap) / len(ref_tokens)
    if precision + recall == 0:
        return 0.0
    return round(2 * precision * recall / (precision + recall), 4)


def main() -> None:
    os.makedirs(MODELS_DIR, exist_ok=True)

    if not os.path.exists(DATA_FILE):
        print(f"[WARN] Dataset not found: {DATA_FILE}")
        print("       Cannot evaluate without real chatbot conversation data.")
        print("       Run chatbot interactions first to generate evaluation data.")
        # Create a placeholder empty results file
        result = {
            "evaluated_at": datetime.now(UTC).isoformat(),
            "dataset_missing": True,
            "total_conversations": 0,
            "bleu_mean": 0.0,
            "rouge1_f1_mean": 0.0,
            "semantic_similarity_mean": 0.0,
            "intent_accuracy": 0.0,
        }
        with open(RESULTS_FILE, "w") as f:
            json.dump(result, f, indent=2)
        print(f"[WARN] Wrote empty results to {RESULTS_FILE}")
        return

    print(f"[INFO] Loading dataset: {DATA_FILE}")
    df = pd.read_csv(DATA_FILE)
    print(f"[INFO] Loaded {len(df):,} conversations")

    required_cols = ["user_message", "expected_response", "actual_response"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        print(f"[ERROR] Missing columns: {missing}")
        sys.exit(1)

    # Drop rows with missing responses
    df = df.dropna(subset=required_cols)
    print(f"[INFO] {len(df):,} rows with complete data")

    # ── Lexical metrics ──────────────────────────────────────────────────────
    print("\n[INFO] Computing BLEU and ROUGE scores…")
    bleu_scores, rouge_scores = [], []
    for _, row in df.iterrows():
        ref = str(row["expected_response"])
        hyp = str(row["actual_response"])
        bleu_scores.append(_compute_simple_bleu(ref, hyp))
        rouge_scores.append(_compute_simple_rouge1(ref, hyp))

    bleu_mean = float(np.mean(bleu_scores))
    rouge_mean = float(np.mean(rouge_scores))
    print(f"[METRICS] BLEU-1 = {bleu_mean:.4f}")
    print(f"[METRICS] ROUGE-1 F1 = {rouge_mean:.4f}")

    # ── Semantic similarity ──────────────────────────────────────────────────
    semantic_mean = 0.0
    try:
        from sentence_transformers import SentenceTransformer
        from sklearn.metrics.pairwise import cosine_similarity
        print("\n[INFO] Computing semantic similarity (all-MiniLM-L6-v2)…")
        model = SentenceTransformer("all-MiniLM-L6-v2")
        expected_emb = model.encode(df["expected_response"].tolist(), show_progress_bar=True)
        actual_emb = model.encode(df["actual_response"].tolist(), show_progress_bar=True)
        sims = [
            float(cosine_similarity([expected_emb[i]], [actual_emb[i]])[0][0])
            for i in range(len(df))
        ]
        semantic_mean = float(np.mean(sims))
        print(f"[METRICS] Semantic Similarity = {semantic_mean:.4f}")
    except ImportError:
        print("[WARN] sentence-transformers not available — skipping semantic similarity")

    # ── Intent classification accuracy ───────────────────────────────────────
    intent_accuracy = 0.0
    if "intent_label" in df.columns:
        print("\n[INFO] Evaluating intent classifier…")
        predicted_intents = df["user_message"].apply(classify_intent)
        true_intents = df["intent_label"]
        intent_accuracy = float((predicted_intents == true_intents).mean())
        print(f"[METRICS] Intent Accuracy = {intent_accuracy:.4f}")

        # Per-intent breakdown
        print("\n[INFO] Per-intent ROUGE scores:")
        per_intent: dict[str, dict] = {}
        for intent in true_intents.unique():
            mask = true_intents == intent
            if mask.sum() == 0:
                continue
            intent_rouge = [rouge_scores[i] for i, m in enumerate(mask) if m]
            per_intent[intent] = {
                "count": int(mask.sum()),
                "rouge1_f1_mean": round(float(np.mean(intent_rouge)), 4),
            }
            print(f"       {intent:30s} n={mask.sum():5d}  ROUGE={np.mean(intent_rouge):.4f}")

    # ── Quality score distribution ────────────────────────────────────────────
    quality_dist: dict = {}
    if "response_quality_score" in df.columns:
        scores = pd.to_numeric(df["response_quality_score"], errors="coerce").dropna()
        quality_dist = {
            "mean": round(float(scores.mean()), 3),
            "std":  round(float(scores.std()), 3),
            "p25":  round(float(scores.quantile(0.25)), 3),
            "p50":  round(float(scores.quantile(0.50)), 3),
            "p75":  round(float(scores.quantile(0.75)), 3),
        }
        print(f"\n[METRICS] Quality Score — mean={quality_dist['mean']:.3f}  p50={quality_dist['p50']:.3f}")

    # ── Model usage breakdown ────────────────────────────────────────────────
    model_usage: dict = {}
    if "model_used" in df.columns:
        model_usage = df["model_used"].value_counts().to_dict()
        print(f"\n[INFO] Model usage: {model_usage}")

    # ── Save results ──────────────────────────────────────────────────────────
    results = {
        "evaluated_at": datetime.now(UTC).isoformat(),
        "total_conversations": len(df),
        "bleu_mean": round(bleu_mean, 4),
        "rouge1_f1_mean": round(rouge_mean, 4),
        "semantic_similarity_mean": round(semantic_mean, 4),
        "intent_accuracy": round(intent_accuracy, 4),
        "quality_distribution": quality_dist,
        "model_usage": {str(k): int(v) for k, v in model_usage.items()},
        "per_intent": per_intent if "intent_label" in df.columns else {},
    }
    with open(RESULTS_FILE, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n[OK]   Results saved to: {RESULTS_FILE}")
    print("[DONE] CHATBOT EVALUATION COMPLETE")


if __name__ == "__main__":
    main()
