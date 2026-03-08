# NeuralOps — AI DevOps / SRE Intelligence Platform

> **Autonomous AI Site Reliability Engineer** — monitors AWS, Azure, and GCP, detects anomalies with ML, performs Root Cause Analysis via Gemini 1.5 Flash, executes safe automated remediation, and self-learns from every incident.

---

## 🚀 How to Run NeuralOps

Follow these steps to get the full platform running with all AI features:

### 1. Prerequisites
- **Docker & Docker Compose**
- **Ollama** (for Phi-3 fallback)
- **Gemini API Key** (optional, but recommended for primary LLM)

### 2. Infrastructure Setup
```bash
# Start MongoDB, Redis, and Ollama services
docker-compose up -d mongodb redis ollama
```

### 3. AI Model Preparation
NeuralOps automatically detects missing models and trains them on startup, but you can trigger it manually:
```bash
# Verify Phi-3 Model is pulled (for fallback)
docker exec -it neuralops-ollama-1 ollama pull phi3

# Run all training scripts (Dataset Integration)
python training/train_anomaly_models.py
python training/train_log_classifier.py
python training/seed_chromadb.py
python training/train_incident_classifier.py
python training/train_rca_model.py
python training/train_remediation_recommender.py
```

### 4. Start the Application
```bash
# Install dependencies
npm install
pip install -e .

# Start Backend & Frontend
npm run dev
```

## 🔍 How to verify Phi-3 is installed and working

NeuralOps uses Phi-3 as a high-performance local fallback for the Gemini Chatbot and for specialized code error detection.

**To verify it is working:**
1. **API Check**: Visit `http://localhost:8000/api/v1/health/phi3`. You should see `{"status": "ready", "model": "phi3"}`.
2. **Dashboard**: Go to **Settings > Integrations**. Look for the **Phi-3 AI Engine** card. It should show a green **Ready** status.
3. **CLI Check**: Run `docker exec -it neuralops-ollama-1 ollama list`. You should see `phi3` in the output.
4. **Chatbot Test**: If you disconnect from the internet or invalidate your Gemini key, the Chatbot header will change to **Standard Mode · NeuralOps AI**, indicating it has successfully failed over to Phi-3.

---

## 🛠️ Key Features Fixed
- **Real Error Detection**: MongoDB + RL feedback loop integrated into `Developer > Issues`.
- **Gemini Stability**: Stream connection issues permanently resolved with REST fallback.
- **Dataset Integration**: 6 specialized training models integrated for SRE intelligence.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Dashboard (React 18)                   │
│          REST/WebSocket → FastAPI Gateway :8000          │
└──────────────┬──────────────────────────┬───────────────┘
               │                          │
    ┌──────────▼──────────┐   ┌──────────▼──────────┐
    │  Orchestrator :8020  │   │  Memory Module :8060  │
    │  (Incident mgmt)     │   │  (ChromaDB RAG)       │
    └──────────┬──────────┘   └──────────────────────┘
               │
    ┌──────────▼──────────┐   ┌──────────────────────┐
    │  ML Engine :8010     │   │  RCA Engine :8040     │
    │  LSTM + IF + Prophet │   │  Gemini / Phi-3 LLM  │
    └──────────┬──────────┘   └──────────────────────┘
               │
    ┌──────────▼──────────┐   ┌──────────────────────┐
    │  Ingestion :8050     │   │  Action Executor:8030 │
    │  OTel Collector      │   │  kubectl / ASG / Jira │
    └──────────┬──────────┘   └──────────────────────┘
               │
    ┌──────────▼──────────────────────────────────────┐
    │           Cloud Connectors                       │
    │    AWS CloudWatch · Azure Monitor · GCP Logging  │
    └──────────────────────────────────────────────────┘
```

### Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, FastAPI, Uvicorn, Pydantic v2 |
| ML | PyTorch 2.0 (LSTM), scikit-learn (Isolation Forest), Prophet |
| LLM | Google Gemini 1.5 Flash (primary), Phi-3 Mini via Ollama (fallback) |
| Database | PostgreSQL 15, ChromaDB (vector), Redis 7 |
| Cloud | AWS boto3, Azure SDK, GCP client libraries |
| DevOps | Slack SDK, PagerDuty Events API v2, Jira REST API v3, GitHub API |
| Frontend | React 18, TypeScript, Vite, Recharts, React Router v6 |
| Infra | Docker Compose, OpenTelemetry Collector |

---

## Quick Start

### Prerequisites
- Docker 24+ and Docker Compose
- Python 3.11+ (for local development)
- Node.js 20+ (for frontend development)

### 1. Clone and Configure

```bash
git clone <repo>
cd neuralops
cp .env.example .env
# Edit .env with your credentials (see Configuration below)
```

### 2. Start Infrastructure

```bash
docker compose up -d postgres redis chromadb
```

### 3. Initialize Database

```bash
docker compose exec postgres psql -U neuralops -d neuralops -f /docker-entrypoint-initdb.d/init_db.sql
# OR run directly:
psql -h localhost -U neuralops -d neuralops -f init_db.sql
```

### 4. Generate Training Data & Train Models

```bash
pip install -e ".[dev]"
python -m training.generate_dataset
python -m training.train --epochs 100
```

### 5. Start All Services

```bash
docker compose up -d
```

### 6. Start Frontend

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:3000** — login with credentials from your `.env`.

---

## Configuration

Copy `.env.example` to `.env` and configure:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `GEMINI_API_KEY` | Google AI Studio API key ([get here](https://aistudio.google.com)) |
| `JWT_SECRET_KEY` | Random 32+ char string for JWT signing |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | AWS credentials (or use IAM role) |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID |
| `GCP_PROJECT_ID` | GCP project ID |
| `SLACK_BOT_TOKEN` | Slack bot OAuth token |
| `PAGERDUTY_SERVICE_KEY` | PagerDuty Events API integration key |
| `JIRA_BASE_URL` / `JIRA_API_TOKEN` | Jira Cloud credentials |
| `GITHUB_TOKEN` | GitHub personal access token |

---

## Service Ports

| Service | Port | Description |
|---------|------|-------------|
| Dashboard API | 8000 | REST + WebSocket gateway |
| ML Engine | 8010 | Anomaly detection service |
| Orchestrator | 8020 | Incident management |
| Action Executor | 8030 | Automated remediation |
| RCA Engine | 8040 | AI root cause analysis |
| Ingestion | 8050 | Telemetry collection |
| Memory | 8060 | ChromaDB vector store |
| PostgreSQL | 5432 | Persistent storage |
| Redis | 6379 | Streams + cache |
| ChromaDB | 8200 | Vector embeddings |
| Ollama | 11434 | Local LLM (Phi-3) |
| OTel Collector | 4317/4318 | OTLP receiver |
| Frontend | 3000 | React dashboard |

---

## API Reference

### Auth
```
POST /auth/login  { email, password } → { access_token }
```

### Incidents
```
GET  /api/v1/incidents?status=&severity=&limit=&offset=
GET  /api/v1/incidents/{id}
PATCH /api/v1/incidents/{id}/status  { status }
POST /api/v1/incidents/{id}/feedback { is_false_positive, mttr_minutes }
GET  /api/v1/incidents/{id}/rca
```

### Anomalies
```
GET  /api/v1/anomalies?service=&limit=
```

### Actions
```
POST /api/v1/actions  { action_type, incident_id, parameters, ... }
GET  /api/v1/actions/audit?incident_id=
```

### AI Chatbot (SSE streaming)
```
POST /api/v1/chat  { message, session_id?, context_incident_id? }
  → text/event-stream  data: {"token": "..."}  data: {"done": true}
GET  /api/v1/chat/{session_id}/history
```

### Real-time WebSocket
```
ws://host/ws/incidents  — Live incident events
ws://host/ws/anomalies  — Live anomaly stream
```

---

## ML Models

### LSTM Autoencoder
- Architecture: 2-layer LSTM + linear decoder  
- Training: reconstruction error on normal time-series sequences  
- Feature vector: 12 metrics (CPU, memory, latency, error_rate, etc.)  
- Threshold: 95th percentile of validation reconstruction error  
- Online learning: updates after every incident resolution  

### Isolation Forest
- Contamination: configurable (default 5%)  
- Features: same 12-metric vector + StandardScaler preprocessing  
- Score normalization: 0–1 via sigmoid transform  

### Hybrid Fusion
```
final_score = 0.6 × lstm_score + 0.4 × isolation_forest_score
```

### Prophet Forecaster  
- Horizon: 30 minutes ahead, 1-minute resolution  
- Per service-metric pair model  
- Detects breach of ±2σ prediction interval  

---

## Supported Remediation Actions

| Action | Description | Requires Approval |
|--------|-------------|-------------------|
| `kubectl_rollout_restart` | Restart a deployment | P1/P2 High confidence: no |
| `kubectl_scale` | Scale a deployment | Always for scale-down |
| `aws_asg_scale` | Scale an Auto Scaling Group | Yes |
| `slack_notification` | Post Slack message | Never |
| `pagerduty_alert` | Trigger PagerDuty incident | Never |
| `jira_create_ticket` | Create Jira issue | Never |
| `cache_flush` | Flush Redis cache prefix | Yes |
| `webhook` | POST to custom endpoint | Configurable |
| `ansible_playbook` | Run Ansible playbook | Always |

---

## Incident Lifecycle

```
Anomaly Detected (ML Engine)
    ↓
Correlation Window (Orchestrator) → Incident Created
    ↓
RCA Triggered (Gemini/Phi-3 analysis)
    ↓
Remediation Actions (Action Executor) → Audit Trail
    ↓
Notifications (Slack / PagerDuty / Jira)
    ↓
Resolution + Feedback → Memory Store (self-learning)
```

---

## Training Data

Generate synthetic training data:

```bash
# Generate 5k normal + 500 anomaly samples + 12 simulation scenarios
python -m training.generate_dataset

# Train models
python -m training.train --epochs 200 --min-samples 2000

# Use custom dataset
python -m training.train --dataset path/to/your/data.csv
```

---

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v --cov=modules --cov=shared

# Run individual services locally
uvicorn modules.api.main:app --port 8000 --reload
uvicorn modules.ml_engine.detector:app --port 8010 --reload
uvicorn modules.orchestrator.service:app --port 8020 --reload

# Frontend dev server with hot reload
cd frontend && npm run dev
```

---

## Project Structure

```
neuralops/
├── modules/
│   ├── ingestion/        # OTel + cloud telemetry consumer
│   ├── ml_engine/        # LSTM, Isolation Forest, Prophet
│   ├── orchestrator/     # Incident correlation + lifecycle
│   ├── rca_engine/       # LLM-powered root cause analysis
│   ├── action_executor/  # Safe automated remediation
│   ├── memory/           # ChromaDB vector store
│   ├── chatbot/          # Streaming AI assistant
│   └── api/              # Dashboard REST + WebSocket API
├── shared/
│   ├── schemas.py        # Canonical Pydantic schemas
│   ├── interfaces.py     # Abstract base classes
│   ├── config.py         # Centralized settings
│   └── llm/              # Gemini + Phi-3 providers
├── connectors/
│   ├── aws/              # CloudWatch, EC2, RDS
│   ├── azure/            # Azure Monitor, Log Analytics
│   └── gcp/              # Cloud Monitoring, Cloud Logging
├── integrations/
│   ├── slack/            # Block-kit alerts + RCA threads
│   ├── pagerduty/        # Events API v2
│   ├── jira/             # Issues + transitions
│   └── github/           # Deployments + Issues
├── training/
│   ├── train.py          # Model training pipeline
│   └── generate_dataset.py # Synthetic data generator
├── frontend/             # React 18 + TypeScript dashboard
├── init_db.sql           # PostgreSQL schema
├── docker-compose.yml    # Full stack deployment
└── .env.example          # Configuration template
```

---

## License

MIT — See LICENSE file.
