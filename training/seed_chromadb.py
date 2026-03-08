"""
training/seed_chromadb.py
──────────────────────────
Dataset 3: training/data/incidents_training_dataset.csv
Columns:  incident_id, title, description, severity, primary_service,
          root_cause_category, root_cause_description,
          remediation_steps_taken, duration_minutes, resolved

Seeds the ChromaDB 'historical_incidents' collection with SRE knowledge
using sentence-transformers (all-MiniLM-L6-v2) for embeddings.
Also seeds a 'runbooks' collection if runbook data is present.
"""
from __future__ import annotations

import os
import sys
import uuid

import numpy as np
import pandas as pd

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "incidents_training_dataset.csv")
# Also check for the RCA QA dataset to seed a Q&A knowledge base
RCA_FILE = os.path.join(os.path.dirname(__file__), "data", "rca_qa_dataset.csv")

CHROMA_HOST = os.environ.get("CHROMADB_HOST", "localhost")
CHROMA_PORT = int(os.environ.get("CHROMADB_PORT", "8100"))

INCIDENT_COLLECTION = "historical_incidents"
RUNBOOK_COLLECTION = "neuralops_runbooks"


def _generate_synthetic_incidents() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    services = ["auth-service", "payment-api", "notification-service", "data-pipeline", "api-gateway"]
    root_causes = ["memory_leak", "database_overload", "network_partition", "cpu_spike", "disk_full"]
    remediations = [
        "Restarted affected pods and increased memory limits",
        "Ran VACUUM on slow tables, added missing indexes",
        "Failed over to backup region, updated BGP routes",
        "Scaled out deployment from 3 to 10 replicas",
        "Cleared log files, expanded persistent volume claim",
    ]
    rows = []
    for i in range(300):
        idx = rng.integers(0, len(root_causes))
        rows.append({
            "incident_id": f"INC-{i+1000:05d}",
            "title": f"{root_causes[idx].replace('_', ' ').title()} in {services[rng.integers(0, len(services))]}",
            "description": f"Service degradation detected due to {root_causes[idx]}. Customers impacted.",
            "severity": rng.choice(["P1", "P2", "P3"]),
            "primary_service": services[rng.integers(0, len(services))],
            "root_cause_category": root_causes[idx],
            "root_cause_description": f"Excessive {root_causes[idx].replace('_', ' ')} caused service to degrade",
            "remediation_steps_taken": remediations[idx],
            "duration_minutes": int(rng.integers(5, 360)),
        })
    return pd.DataFrame(rows)


def main() -> None:
    try:
        import chromadb
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        print(f"[ERROR] Missing dependency: {exc}")
        print("        Install: pip install chromadb sentence-transformers")
        sys.exit(1)

    try:
        chroma = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
        chroma.heartbeat()
        print(f"[OK]   Connected to ChromaDB at {CHROMA_HOST}:{CHROMA_PORT}")
    except Exception as exc:
        print(f"[ERROR] Cannot reach ChromaDB: {exc}")
        sys.exit(1)

    print("[INFO] Loading embedding model: all-MiniLM-L6-v2…")
    model = SentenceTransformer("all-MiniLM-L6-v2")

    # ── Seed historical_incidents ─────────────────────────────────────────────
    if not os.path.exists(DATA_FILE):
        print(f"[WARN] Incidents dataset not found: {DATA_FILE}")
        print("       Generating synthetic incidents…")
        df = _generate_synthetic_incidents()
    else:
        print(f"[INFO] Loading incidents dataset: {DATA_FILE}")
        df = pd.read_csv(DATA_FILE)

    print(f"[INFO] Loaded {len(df):,} incidents")

    col = chroma.get_or_create_collection(INCIDENT_COLLECTION)
    existing = col.count()
    print(f"[INFO] Collection '{INCIDENT_COLLECTION}' has {existing} existing documents")
    if existing > 0:
        print("[SKIP] Collection already seeded — delete it to re-seed")
    else:
        # Build document text by combining title + description + root cause
        docs = []
        metadatas = []
        ids = []
        for _, row in df.iterrows():
            text = (
                f"Title: {row.get('title', '')}\n"
                f"Service: {row.get('primary_service', '')}\n"
                f"Severity: {row.get('severity', '')}\n"
                f"Description: {row.get('description', '')}\n"
                f"Root Cause: {row.get('root_cause_description', row.get('root_cause_category', ''))}\n"
                f"Remediation: {row.get('remediation_steps_taken', '')}"
            )
            docs.append(text)
            metadatas.append({
                "incident_id": str(row.get("incident_id", "")),
                "severity": str(row.get("severity", "")),
                "primary_service": str(row.get("primary_service", "")),
                "root_cause_category": str(row.get("root_cause_category", "")),
                "remediation_steps_taken": str(row.get("remediation_steps_taken", ""))[:500],
                "duration_minutes": int(row.get("duration_minutes", 0)),
            })
            ids.append(str(row.get("incident_id", str(uuid.uuid4()))))

        # Batch embed and upsert
        batch_size = 64
        for i in range(0, len(docs), batch_size):
            batch_docs = docs[i:i+batch_size]
            batch_metas = metadatas[i:i+batch_size]
            batch_ids = ids[i:i+batch_size]
            embeddings = model.encode(batch_docs, show_progress_bar=False).tolist()
            col.upsert(documents=batch_docs, embeddings=embeddings, metadatas=batch_metas, ids=batch_ids)
            print(f"[INFO] Upserted {min(i+batch_size, len(docs))}/{len(docs)} incidents…")

        print(f"[OK]   Seeded {len(docs)} incidents into '{INCIDENT_COLLECTION}'")

    # ── Seed RCA QA knowledge base ─────────────────────────────────────────────
    if os.path.exists(RCA_FILE):
        rca_df = pd.read_csv(RCA_FILE)
        print(f"\n[INFO] Loading RCA QA dataset: {RCA_FILE} ({len(rca_df):,} rows)")
        qa_col = chroma.get_or_create_collection("rca_qa_knowledge")
        qa_exist = qa_col.count()
        if qa_exist > 0:
            print(f"[SKIP] 'rca_qa_knowledge' already has {qa_exist} docs")
        else:
            qa_docs = []
            qa_metas = []
            qa_ids = []
            for _, row in rca_df.iterrows():
                q = str(row.get("question", row.get("symptom", "")))
                a = str(row.get("answer", row.get("root_cause", "")))
                qa_docs.append(f"Q: {q}\nA: {a}")
                qa_metas.append({
                    "category": str(row.get("category", row.get("root_cause_category", "general"))),
                    "question": q[:300],
                    "answer": a[:500],
                })
                qa_ids.append(str(uuid.uuid4()))

            for i in range(0, len(qa_docs), batch_size):
                batch_docs = qa_docs[i:i+batch_size]
                batch_metas = qa_metas[i:i+batch_size]
                batch_ids = qa_ids[i:i+batch_size]
                embeddings = model.encode(batch_docs, show_progress_bar=False).tolist()
                qa_col.upsert(documents=batch_docs, embeddings=embeddings, metadatas=batch_metas, ids=batch_ids)
            print(f"[OK]   Seeded {len(qa_docs)} RCA QA pairs into 'rca_qa_knowledge'")

    print("\n[DONE] CHROMADB SEEDING COMPLETE")


if __name__ == "__main__":
    main()
