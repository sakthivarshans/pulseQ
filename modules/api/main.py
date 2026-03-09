"""
modules/api/main.py
────────────────────
NeuralOps Dashboard API — complete FastAPI application.

Features:
  - JWT authentication (access + refresh tokens)
  - REST endpoints for incidents, anomalies, RCA, actions, SLOs
  - Real GitHub repository analysis (via integrations/github/repo_analyzer.py)
  - Real system metrics via psutil
  - Chatbot SSE streaming — works WITHOUT Redis
  - Issue suggestion upvote/downvote for RL feedback loop
  - Gemini health check endpoint
  - Background repo polling for connection stability
  - Prometheus metrics exposure
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, AsyncGenerator, Optional

import structlog
import uvicorn
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

try:
    import motor.motor_asyncio as motor_asyncio
    from bson import ObjectId
    from bson.errors import InvalidId
    _MOTOR_OK = True
except ImportError:
    _MOTOR_OK = False
    ObjectId = None

try:
    from prometheus_client import Counter, generate_latest
    _PROMETHEUS_OK = True
except ImportError:
    _PROMETHEUS_OK = False

try:
    import redis.asyncio as aioredis
    _REDIS_LIB_OK = True
except ImportError:
    _REDIS_LIB_OK = False

try:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker
    _SQLALCHEMY_OK = True
except ImportError:
    _SQLALCHEMY_OK = False

from shared.config import get_settings
from shared.schemas import ActionRequest, IncidentStatus

# ── New routers (imported after app creation) ──────────────────────────────────
# They are included inside lifespan or after app is defined to avoid circular imports

logger = structlog.get_logger(__name__)
settings = get_settings()

# ── Security ───────────────────────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)

if _PROMETHEUS_OK:
    API_REQUESTS = Counter("neuralops_api_requests_total", "API request count", ["path", "method"])

# ── Global state ───────────────────────────────────────────────────────────────
_redis = None
_engine = None
_sf = None
_chatbot = None
_ws_connections: dict[str, list[WebSocket]] = {}
_repo_poll_task: asyncio.Task | None = None
_mongo_client = None
_mongo_db = None

# In-memory repository registry: repo_id -> analysis result dict
_repo_registry: dict[str, dict] = {}
_repo_poll_failures: dict[str, int] = {}


# ── Lifespan ───────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    global _redis, _engine, _sf, _chatbot, _repo_poll_task, _mongo_client, _mongo_db

    # Redis (optional)
    if _REDIS_LIB_OK:
        try:
            _redis = aioredis.from_url(
                settings.redis_url, encoding="utf-8", decode_responses=True
            )
            await _redis.ping()
            logger.info("redis_connected")
        except Exception as exc:
            logger.warning("redis_not_available", error=str(exc))
            _redis = None

    # PostgreSQL (optional)
    if _SQLALCHEMY_OK:
        try:
            _engine = create_async_engine(settings.database_url, echo=False, pool_size=5,
                                          pool_pre_ping=True)
            _sf = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
        except Exception as exc:
            logger.warning("db_not_available", error=str(exc))

    # MongoDB Motor (optional — graceful degradation)
    if _MOTOR_OK:
        try:
            _mongo_client = motor_asyncio.AsyncIOMotorClient(
                settings.mongodb_url, serverSelectionTimeoutMS=3000
            )
            await _mongo_client.admin.command("ping")
            _mongo_db = _mongo_client[settings.mongodb_db_name]
            # Ensure indexes exist
            await _ensure_mongo_indexes(_mongo_db)
            logger.info("mongodb_connected", db=settings.mongodb_db_name)
        except Exception as exc:
            logger.warning("mongodb_not_available", error=str(exc))
            _mongo_client = None
            _mongo_db = None

    # Chatbot — works with OR without Redis
    try:
        from modules.chatbot.service import ChatbotService
        _chatbot = ChatbotService(_redis, _mongo_db)
        logger.info("chatbot_initialized")
    except Exception as exc:
        logger.error("chatbot_init_failed", error=str(exc))

    # OpenRouter / LLM startup health check
    try:
        from shared.llm import llm_service
        if llm_service.openrouter_available:
            logger.info(
                "OPENROUTER API KEY CONFIGURED",
                model=llm_service.model,
            )
        else:
            logger.warning(
                "OPENROUTER_API_KEY not set — chatbot will use Phi-3 fallback only"
            )
    except Exception as exc:
        logger.warning("llm_service_init_warning", error=str(exc))

    # Auto-train anomaly models if missing
    await _ensure_models_trained()

    # Start background system metrics collector
    try:
        from modules.ingestion.collectors.system_metrics import start_collector
        asyncio.create_task(start_collector())
        logger.info("metrics_collector_started")
    except Exception as exc:
        logger.warning("metrics_collector_failed", error=str(exc))

    # Start repository polling background task
    _repo_poll_task = asyncio.create_task(_repo_poll_loop())

    # Start website monitor background task
    if _sf is not None:
        try:
            from modules.api.background.website_monitor import poll_websites
            asyncio.create_task(poll_websites(_sf))
            logger.info("website_monitor_started")
        except Exception as exc:
            logger.warning("website_monitor_failed", error=str(exc))

    # Seed default repositories into PostgreSQL if table is empty
    if _sf is not None:
        try:
            await _seed_default_repositories(_sf)
        except Exception as exc:
            logger.warning("default_repo_seed_failed", error=str(exc))

    # Mount new routers with db_session injected
    try:
        from modules.api.routers import notifications, integrations, reports
        notifications.router.dependencies = []
        integrations.router.dependencies = []
        reports.router.dependencies = []

        # Provide session factory to routers via dependency override pattern
        # Each router endpoint accepts db_session=None and we pass _sf
        _mount_routers_with_session()
    except Exception as exc:
        logger.warning("router_mount_failed", error=str(exc))

    logger.info("dashboard_api_ready", chatbot=(_chatbot is not None))
    yield

    if _repo_poll_task:
        _repo_poll_task.cancel()
    if _redis:
        await _redis.aclose()
    if _engine:
        await _engine.dispose()
    if _mongo_client:
        _mongo_client.close()


async def _ensure_mongo_indexes(db: Any) -> None:
    """Create required MongoDB indexes — idempotent."""
    try:
        # repo_errors indexes
        await db["repo_errors"].create_index([("repo_id", 1), ("file_path", 1)])
        await db["repo_errors"].create_index([("repo_id", 1), ("severity", 1)])
        await db["repo_errors"].create_index([("repo_id", 1), ("error_type", 1)])
        await db["repo_errors"].create_index([("analysis_id", 1)])
        # error_feedback unique index
        await db["error_feedback"].create_index(
            [("error_id", 1), ("user_id", 1)], unique=True
        )
        # rl_weights unique index
        await db["rl_weights"].create_index([("error_type", 1)], unique=True)
        # chatbot_context_cache TTL index (300 seconds)
        await db["chatbot_context_cache"].create_index(
            [("created_at", 1)], expireAfterSeconds=300
        )
    except Exception as exc:
        logger.warning("mongo_index_error", error=str(exc))


async def _ensure_models_trained() -> None:
    """Auto-run training scripts if model files are missing."""
    models_dir = os.path.abspath("./models")
    os.makedirs(models_dir, exist_ok=True)

    anomaly_model = os.path.join(models_dir, "isolation_forest_anomaly.pkl")
    log_model = os.path.join(models_dir, "log_anomaly_classifier.pkl")

    if not os.path.exists(anomaly_model):
        script = os.path.abspath("./training/train_anomaly_models.py")
        if os.path.exists(script):
            logger.info("TRAINING ANOMALY MODELS FROM DATASET - THIS MAY TAKE A FEW MINUTES")
            try:
                await asyncio.to_thread(
                    subprocess.run,
                    [sys.executable, script],
                    timeout=600,
                    capture_output=True,
                )
            except Exception as exc:
                logger.warning("anomaly_training_failed", error=str(exc))
    else:
        logger.info("ANOMALY MODELS LOADED FROM DISK")

    if not os.path.exists(log_model):
        script = os.path.abspath("./training/train_log_classifier.py")
        if os.path.exists(script):
            logger.info("TRAINING LOG CLASSIFIER FROM DATASET")
            try:
                await asyncio.to_thread(
                    subprocess.run,
                    [sys.executable, script],
                    timeout=300,
                    capture_output=True,
                )
            except Exception as exc:
                logger.warning("log_training_failed", error=str(exc))

    # Seed ChromaDB if historical_incidents collection is empty
    await _ensure_chromadb_seeded()


async def _ensure_chromadb_seeded() -> None:
    """Auto-run seed_chromadb.py if historical_incidents is empty."""
    try:
        import chromadb
        chroma_client = chromadb.HttpClient(
            host=settings.chromadb_host, port=settings.chromadb_port
        )
        col = chroma_client.get_or_create_collection("historical_incidents")
        count = col.count()
        if count == 0:
            script = os.path.abspath("./training/seed_chromadb.py")
            if os.path.exists(script):
                logger.info("SEEDING CHROMADB FROM INCIDENTS DATASET")
                await asyncio.to_thread(
                    subprocess.run,
                    [sys.executable, script],
                    timeout=600,
                    capture_output=True,
                )
        else:
            logger.info("CHROMADB historical_incidents already seeded", count=count)
    except Exception as exc:
        logger.debug("chromadb_seed_check_skipped", reason=str(exc))


app = FastAPI(
    title="NeuralOps Dashboard API",
    version="2.0.0",
    description="REST + WebSocket + SSE API for the NeuralOps Dashboard",
    lifespan=lifespan,
)


def _mount_routers_with_session() -> None:
    """Include new routers and wire them up with the global session factory."""
    from modules.api.routers import notifications as notif_router
    from modules.api.routers import integrations as integ_router
    from modules.api.routers import reports as reports_router
    from modules.api.routers import predictions as predictions_router

    notif_router.router.dependencies = []
    integ_router.router.dependencies = []
    reports_router.router.dependencies = []
    predictions_router.router.dependencies = []

    # Inject session factory into each router via default kwarg
    # (each endpoint accepts db_session=None and we provide _sf)
    for route in predictions_router.router.routes:
        pass  # FastAPI resolves default kwargs at call time

    app.include_router(notif_router.router)
    app.include_router(integ_router.router)
    app.include_router(reports_router.router)
    app.include_router(predictions_router.router)


async def _seed_default_repositories(sf) -> None:
    """Insert the three permanent sakthivarshans repositories with fixed UUIDs."""
    defaults = [
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "name": "Bug-Detection-and-Fixing-Model",
            "owner": "sakthivarshans",
            "repo_url": "https://github.com/sakthivarshans/Bug-Detection-and-Fixing-Model.git",
            "description": "Bug Detection and Fixing Model",
            "primary_language": "Python",
            "platform": "github",
        },
        {
            "id": "00000000-0000-0000-0000-000000000002",
            "name": "Diabetes-Prediction-Model",
            "owner": "sakthivarshans",
            "repo_url": "https://github.com/sakthivarshans/Diabetes-Prediction-Model.git",
            "description": "Diabetes Prediction Model",
            "primary_language": "Python",
            "platform": "github",
        },
        {
            "id": "00000000-0000-0000-0000-000000000003",
            "name": "Noether-Duplicated",
            "owner": "sakthivarshans",
            "repo_url": "https://github.com/sakthivarshans/Noether-Duplicated.git",
            "description": "Noether Duplicated Project",
            "primary_language": "Python",
            "platform": "github",
        },
    ]
    try:
        async with sf() as session:
            # Ensure columns exist before inserting
            await session.execute(text("ALTER TABLE repositories ADD COLUMN IF NOT EXISTS description TEXT"))
            await session.execute(text("ALTER TABLE repositories ADD COLUMN IF NOT EXISTS primary_language TEXT"))
            await session.commit()

        async with sf() as session:
            for r in defaults:
                await session.execute(
                    text(
                        "INSERT INTO repositories "
                        "(id, name, owner, repo_url, description, primary_language, platform, is_default, status) "
                        "VALUES (:id, :name, :owner, :repo_url, :description, :primary_language, :platform, TRUE, 'connected') "
                        "ON CONFLICT (repo_url) DO UPDATE SET "
                        "  id = EXCLUDED.id, "
                        "  is_default = TRUE, "
                        "  primary_language = EXCLUDED.primary_language, "
                        "  description = EXCLUDED.description"
                    ),
                    r,
                )
            await session.commit()

        # Seed predictions for default repos if none exist
        async with sf() as session:
            # Create predictions table if not exists
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS predictions (
                    id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    repo_id               UUID REFERENCES repositories(id) ON DELETE CASCADE,
                    service_name          TEXT NOT NULL DEFAULT 'unknown',
                    prediction_type       TEXT NOT NULL,
                    description           TEXT,
                    confidence            FLOAT NOT NULL DEFAULT 0.5,
                    status                TEXT NOT NULL DEFAULT 'active',
                    estimated_impact_time TIMESTAMPTZ,
                    snoozed_until         TIMESTAMPTZ,
                    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """))
            await session.commit()

        async with sf() as session:
            result = await session.execute(
                text("SELECT COUNT(*) FROM predictions WHERE repo_id IN ("
                     "'00000000-0000-0000-0000-000000000001',"
                     "'00000000-0000-0000-0000-000000000002',"
                     "'00000000-0000-0000-0000-000000000003')")
            )
            pred_count = result.scalar() or 0
            if pred_count == 0:
                from datetime import UTC, timedelta
                seed_preds = [
                    {
                        "repo_id": "00000000-0000-0000-0000-000000000001",
                        "service_name": "Bug-Detection-and-Fixing-Model",
                        "prediction_type": "high_error_rate",
                        "description": "Error rate trending upward in bug detection pipeline. Model inference failures expected to increase.",
                        "confidence": 0.87,
                    },
                    {
                        "repo_id": "00000000-0000-0000-0000-000000000002",
                        "service_name": "Diabetes-Prediction-Model",
                        "prediction_type": "memory_exhaustion",
                        "description": "Memory usage growing during batch prediction. OOM risk if dataset size increases.",
                        "confidence": 0.79,
                    },
                    {
                        "repo_id": "00000000-0000-0000-0000-000000000003",
                        "service_name": "Noether-Duplicated",
                        "prediction_type": "cpu_spike",
                        "description": "CPU usage elevated during duplicate detection runs. Performance degradation expected under load.",
                        "confidence": 0.91,
                    },
                ]
                offsets_hours = [2, 4, 1]
                for pred, offset_h in zip(seed_preds, offsets_hours):
                    await session.execute(
                        text(
                            "INSERT INTO predictions "
                            "(repo_id, service_name, prediction_type, description, confidence, status, estimated_impact_time) "
                            "VALUES (:repo_id, :service_name, :prediction_type, :description, :confidence, 'active', "
                            "NOW() + :offset_interval) "
                        ),
                        {**pred, "offset_interval": f"{offset_h} hours"},
                    )
                await session.commit()

        logger.info("default_repositories_seeded", count=len(defaults))
    except Exception as exc:
        logger.warning("default_repo_seed_failed", error=str(exc))

@app.middleware("http")
async def log_requests(request: Request, call_next):
    # Log incoming request headers for auth debugging
    auth_header = request.headers.get("Authorization", "Missing")
    logger.info("api_request", path=request.url.path, method=request.method, auth=auth_header[:15] if auth_header != "Missing" else "None")
    
    response = await call_next(request)
    
    # Log the response status
    if response.status_code >= 400:
        logger.warning("api_response_error", path=request.url.path, status=response.status_code)
    return response


# CORS: always wildcard in development. allow_credentials MUST be False when using ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Auth helpers ───────────────────────────────────────────────────────────────

def _create_access_token(subject: str, role: str) -> str:
    payload = {
        "sub": subject,
        "role": role,
        "exp": datetime.now(UTC) + timedelta(minutes=settings.jwt_access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


async def _get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict[str, str]:
    if not creds:
        # Dev bypass: allow unauthenticated access with a default admin identity
        return {"user_id": _ADMIN_UID, "role": "admin"}

    # Dev bypass token — skip JWT validation entirely
    if creds.credentials == "dev-bypass-no-auth":
        return {"user_id": _ADMIN_UID, "role": "admin"}

    try:
        payload = jwt.decode(
            creds.credentials, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        # Ensure required fields are present
        if "sub" not in payload:
            raise KeyError("sub")
        if "role" not in payload:
            raise KeyError("role")
            
        return {"user_id": payload["sub"], "role": payload["role"]}
    except JWTError as exc:
        logger.warning("auth_failed_token_invalid", error=str(exc))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Token invalid: {exc}")
    except KeyError as exc:
        logger.warning("auth_failed_missing_field", field=str(exc))
        raise HTTPException(status_code=403, detail=f"Forbidden: Token missing required field {exc}")
    except Exception as exc:
        # Catch other errors (e.g. missing library, malformed token structure, etc)
        err_msg = f"{type(exc).__name__}: {str(exc)}"
        logger.error("auth_system_error", error=err_msg)
        raise HTTPException(status_code=403, detail=f"Forbidden: Auth error - {err_msg}")


# ── Request models ─────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str
    context_incident_id: str | None = None


class RepoAddRequest(BaseModel):
    url: str
    token: str | None = None  # uses .env token if omitted
    name: str | None = None


_ADMIN_CREDENTIALS: dict[str, str] = {
    "admin": "admin123",
    "admin@neuralops.io": "Admin@123",
}
_ADMIN_UID = "00000000-0000-0000-0000-000000000001"


async def _authenticate(username: str, password: str) -> str:
    if _ADMIN_CREDENTIALS.get(username) == password:
        return _create_access_token(_ADMIN_UID, "admin")

    if _sf is not None:
        try:
            async with _sf() as session:
                result = await session.execute(
                    text(
                        "SELECT user_id, hashed_password, role FROM users "
                        "WHERE (email = :u OR username = :u) AND is_active = TRUE"
                    ),
                    {"u": username},
                )
                row = result.mappings().first()
            if row and pwd_context.verify(password, row["hashed_password"]):
                return _create_access_token(str(row["user_id"]), row["role"])
        except Exception:
            pass

    raise HTTPException(status_code=401, detail="Invalid credentials")


# ── Auth routes ────────────────────────────────────────────────────────────────

@app.post("/auth/login", tags=["auth"])
async def login(req: LoginRequest) -> dict[str, str]:
    token = await _authenticate(req.email, req.password)
    return {"access_token": token, "token_type": "bearer"}


@app.post("/api/v1/auth/token", tags=["auth"])
async def oauth2_token(form_data: OAuth2PasswordRequestForm = Depends()) -> dict[str, str]:
    token = await _authenticate(form_data.username, form_data.password)
    return {"access_token": token, "token_type": "bearer"}


@app.get("/api/v1/auth/me", tags=["auth"])
async def auth_me(user: dict = Depends(_get_current_user)) -> dict:
    return {"status": "authenticated", "user": user}


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["observability"])
async def health() -> dict[str, Any]:
    """Full service health check — never fakes healthy status."""
    import time as _time
    from shared.llm import llm_service

    async def _check_postgres() -> dict:
        try:
            if _sf is None:
                return {"status": "error", "error": "PostgreSQL not configured"}
            start = _time.time()
            async with _sf() as sess:
                from sqlalchemy import text as _text
                await sess.execute(_text("SELECT 1"))
            return {"status": "healthy", "response_ms": round((_time.time() - start) * 1000, 1)}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def _check_redis() -> dict:
        try:
            if _redis is None:
                return {"status": "error", "error": "Redis not configured"}
            start = _time.time()
            await _redis.ping()
            return {"status": "healthy", "response_ms": round((_time.time() - start) * 1000, 1)}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def _check_mongodb() -> dict:
        try:
            if _mongo_db is None:
                return {"status": "error", "error": "MongoDB not configured"}
            start = _time.time()
            await _mongo_db.command("ping")
            return {"status": "healthy", "response_ms": round((_time.time() - start) * 1000, 1)}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def _check_chromadb() -> dict:
        try:
            start = _time.time()
            import httpx as _httpx
            host = getattr(settings, 'chromadb_host', 'localhost')
            port = getattr(settings, 'chromadb_port', 8000)
            async with _httpx.AsyncClient(timeout=5.0) as client:
                # Try ChromaDB v2 heartbeat first, fall back to v1
                for path in ("/api/v2/heartbeat", "/api/v1/heartbeat"):
                    try:
                        r = await client.get(f"http://{host}:{port}{path}")
                        if r.status_code < 400:
                            return {"status": "healthy", "response_ms": round((_time.time() - start) * 1000, 1)}
                    except Exception:
                        continue
            return {
                "status": "warning",
                "error": "ChromaDB not reachable (optional — vector search disabled)",
                "fix": "Start ChromaDB: docker run -p 8000:8000 chromadb/chroma",
            }
        except Exception as e:
            return {
                "status": "warning",
                "error": f"ChromaDB unavailable: {e} (optional service)",
                "fix": "Start ChromaDB: docker run -p 8000:8000 chromadb/chroma",
            }

    async def _check_openrouter() -> dict:
        if not settings.openrouter_api_key:
            return {
                "status": "warning",
                "error": "OPENROUTER_API_KEY not set in .env",
                "fix": "Get a free key at openrouter.ai and add it to your .env file",
            }
        try:
            start = _time.time()
            import httpx as _httpx
            async with _httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                )
                r.raise_for_status()
            return {
                "status": "healthy",
                "model": settings.openrouter_model,
                "response_ms": round((_time.time() - start) * 1000, 1),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def _check_phi3() -> dict:
        try:
            start = _time.time()
            import httpx as _httpx
            async with _httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{settings.ollama_base_url}/api/tags")
                models = r.json().get("models", [])
                phi3 = [m for m in models if "phi3" in m.get("name", "")]
                if not phi3:
                    return {
                        "status": "warning",
                        "error": "phi3:mini not installed",
                        "fix": "Run: docker exec neuralops-ollama ollama pull phi3:mini",
                    }
                return {
                    "status": "healthy",
                    "model": phi3[0]["name"],
                    "response_ms": round((_time.time() - start) * 1000, 1),
                }
        except Exception as e:
            return {
                "status": "warning",
                "error": str(e),
                "fix": "Start Ollama: docker run -d -p 11434:11434 ollama/ollama  (optional — OpenRouter is active)",
            }

    checks = await asyncio.gather(
        _check_postgres(),
        _check_redis(),
        _check_mongodb(),
        _check_chromadb(),
        _check_openrouter(),
        _check_phi3(),
        return_exceptions=True,
    )
    labels = ["postgres", "redis", "mongodb", "chromadb", "openrouter", "phi3"]
    service_results: dict[str, Any] = {}
    overall = "healthy"

    # Core services: postgres, redis — if these fail the system is degraded
    # Optional services: mongodb, chromadb, phi3 — warnings are acceptable
    OPTIONAL_SERVICES = {"chromadb", "phi3", "mongodb"}

    for label, result in zip(labels, checks):
        if isinstance(result, Exception):
            service_results[label] = {"status": "warning" if label in OPTIONAL_SERVICES else "error", "error": str(result)}
            if label not in OPTIONAL_SERVICES:
                overall = "degraded"
        else:
            service_results[label] = result
            if result.get("status") == "error" and label not in OPTIONAL_SERVICES:
                overall = "degraded"

    return {
        "status": overall,
        "timestamp": datetime.now(UTC).isoformat(),
        "services": service_results,
        "active_llm": llm_service.model if llm_service.openrouter_available else "phi3:mini",
    }


@app.get("/api/v1/health/llm", tags=["observability"])
async def health_llm() -> dict[str, Any]:
    """Full LLM health check — tests OpenRouter and Phi-3, reports which is active."""
    from shared.llm import llm_service
    return await llm_service.health_check()


@app.get("/api/v1/health/phi3", tags=["observability"])
async def health_phi3() -> dict[str, Any]:
    """Phi-3/Ollama health check: reachability → model list → inference test (30s timeout)."""
    import time as _time
    import httpx as _httpx
    ollama_url = settings.ollama_base_url

    # Step 1: Is Ollama reachable?
    try:
        async with _httpx.AsyncClient(timeout=5) as client:
            tags_resp = await client.get(f"{ollama_url}/api/tags")
            tags_resp.raise_for_status()
            models = tags_resp.json().get("models", [])
    except Exception as exc:
        return {
            "status": "unreachable",
            "error": str(exc),
            "troubleshooting": [
                "Ensure Ollama container is running: docker ps | grep ollama",
                "Check Ollama logs: docker logs neuralops-ollama",
                f"Verify Ollama URL in .env: OLLAMA_BASE_URL={ollama_url}",
            ],
        }

    # Step 2: Is phi3 installed?
    phi3_model = next((m for m in models if m.get("name", "").startswith("phi3")), None)
    if not phi3_model:
        return {
            "status": "not_installed",
            "message": "Phi-3 model not found in Ollama",
            "install_command": "ollama pull phi3:mini",
            "docker_command": "docker exec neuralops-ollama ollama pull phi3:mini",
            "available_models": [m.get("name") for m in models],
        }

    # Step 3: Inference test with 30s timeout
    try:
        t_start = _time.monotonic()
        async with _httpx.AsyncClient(timeout=30.0) as client:
            infer_resp = await client.post(
                f"{ollama_url}/api/generate",
                json={
                    "model": phi3_model["name"],
                    "prompt": "Reply with exactly one word: healthy",
                    "stream": False,
                },
            )
            infer_resp.raise_for_status()
            response_text = infer_resp.json().get("response", "")[:100]
        elapsed_ms = round((_time.monotonic() - t_start) * 1000)
        return {
            "status": "ready",
            "model": phi3_model["name"],
            "model_size": phi3_model.get("size"),
            "response_time_ms": elapsed_ms,
            "test_response": response_text,
        }
    except Exception as exc:
        return {
            "status": "installed_not_responding",
            "model": phi3_model["name"],
            "error": str(exc),
            "fix": f"docker exec neuralops-ollama ollama pull {phi3_model['name']}",
        }


@app.get("/api/v1/chatbot/health", tags=["chatbot"])
async def chatbot_health() -> dict[str, Any]:
    """Test OpenRouter and Phi-3 availability and report which is active."""
    from shared.llm import llm_service
    return await llm_service.health_check()


@app.get("/metrics", response_class=PlainTextResponse, tags=["observability"])
async def prometheus_metrics() -> str:
    if _PROMETHEUS_OK:
        return generate_latest().decode("utf-8")
    return "# psutil metrics not available\n"


# ── System Metrics ─────────────────────────────────────────────────────────────

@app.get("/api/v1/metrics/system", tags=["metrics"])
async def get_system_metrics(
    limit: int = 60,
    _user: dict = Depends(_get_current_user),
) -> dict[str, Any]:
    """Return real system metrics from psutil ring buffer."""
    try:
        from modules.ingestion.collectors.system_metrics import (
            get_latest_metrics,
            get_metrics_buffer,
        )
        buf = get_metrics_buffer()
        latest = get_latest_metrics()
        return {
            "latest": latest,
            "history": buf[-limit:],
            "source": "psutil",
            "info": "Showing NeuralOps server metrics. Connect your app with the NeuralOps SDK to monitor your application.",
        }
    except Exception as exc:
        return {"latest": {}, "history": [], "error": str(exc)}


# ── Repository endpoints ────────────────────────────────────────────────────────

@app.get("/api/v1/repositories", tags=["repositories"])
async def list_repositories(
    project_id: Optional[str] = Query(default=None),
    _user: dict = Depends(_get_current_user),
) -> dict[str, Any]:
    """Return all tracked repositories + default repos from PostgreSQL."""
    repos = []

    # Include DB default repositories
    if _sf is not None:
        try:
            async with _sf() as session:
                db_result = await session.execute(
                    text(
                        "SELECT id, name, owner, url, description, language, platform, "
                        "       is_default, website_url, is_live_monitoring_enabled "
                        "FROM repositories ORDER BY is_default DESC, name ASC"
                    )
                )
                db_repos = db_result.mappings().all()
            for r in db_repos:
                repos.append({
                    "id": str(r["id"]),
                    "repo_id": str(r["id"]),
                    "name": r["name"],
                    "owner": r["owner"],
                    "url": r["url"] or "",
                    "description": r["description"] or "",
                    "language": r["language"] or "Unknown",
                    "platform": r["platform"] or "github",
                    "is_default": r["is_default"],
                    "website_url": r["website_url"],
                    "is_live_monitoring_enabled": r["is_live_monitoring_enabled"],
                    "status": "active",
                    "stars": 0,
                    "total_files": 0,
                    "total_loc": 0,
                    "issues_found": 0,
                    "analyzed_at": None,
                    "last_commit": None,
                })
        except Exception as exc:
            logger.warning("list_repositories_db_error", error=str(exc))

    # Include in-memory analyzed repositories (user-added)
    db_ids = {r["repo_id"] for r in repos}
    for repo_mem_id, data in _repo_registry.items():
        mem_id = data.get("id", repo_mem_id)
        if mem_id in db_ids or repo_mem_id in db_ids:
            continue
        repos.append({
            "id": repo_mem_id,
            "repo_id": repo_mem_id,
            "name": data.get("name", repo_mem_id.split("/")[-1]),
            "owner": data.get("owner", repo_mem_id.split("/")[0]),
            "url": data.get("repo_url", f"https://github.com/{repo_mem_id}"),
            "description": data.get("description", ""),
            "language": data.get("language", "Unknown"),
            "platform": "github",
            "is_default": False,
            "website_url": None,
            "is_live_monitoring_enabled": False,
            "status": data.get("status", "active"),
            "stars": data.get("stars", 0),
            "total_files": data.get("total_files", 0),
            "total_loc": data.get("total_loc", 0),
            "issues_found": data.get("issues_found", 0),
            "analyzed_at": data.get("analyzed_at"),
            "last_commit": data.get("last_commit"),
        })

    if project_id:
        repos = [r for r in repos if r.get("repo_id") == project_id or r.get("id") == project_id]

    return {"repositories": repos, "total": len(repos)}


@app.get("/api/v1/repositories/list", tags=["repositories"])
async def list_repositories_minimal(
    _user: dict = Depends(_get_current_user),
) -> dict[str, Any]:
    """Fast minimal list for the project selector dropdown. No heavy joins."""
    repos: list[dict] = []
    if _sf is not None:
        try:
            async with _sf() as session:
                db_result = await session.execute(
                    text(
                        "SELECT id, name, owner, url, platform, is_default, "
                        "       website_url, is_live_monitoring_enabled, "
                        "       last_commit_hash, last_commit_message "
                        "FROM repositories ORDER BY is_default DESC, created_at ASC"
                    )
                )
                for r in db_result.mappings().all():
                    repos.append({
                        "id": str(r["id"]),
                        "name": r["name"],
                        "owner": r["owner"],
                        "platform": r["platform"] or "github",
                        "status": "active",
                        "website_url": r["website_url"],
                        "is_live_monitoring_enabled": r["is_live_monitoring_enabled"],
                        "last_commit_hash": r.get("last_commit_hash"),
                        "last_commit_message": r.get("last_commit_message"),
                        "is_default": r["is_default"],
                    })
        except Exception as exc:
            logger.warning("list_repositories_minimal_error", error=str(exc))
    # Merge in-memory analyzed repos not in DB
    db_ids = {r["id"] for r in repos}
    for rid, d in _repo_registry.items():
        if rid not in db_ids and str(d.get("id", "")) not in db_ids:
            repos.append({
                "id": rid,
                "name": d.get("name", rid.split("/")[-1]),
                "owner": d.get("owner", rid.split("/")[0] if "/" in rid else "unknown"),
                "platform": "github",
                "status": d.get("status", "active"),
                "website_url": None,
                "is_live_monitoring_enabled": False,
                "last_commit_hash": None,
                "last_commit_message": None,
                "is_default": False,
            })
    return {"repositories": repos, "total": len(repos)}


@app.post("/api/v1/repositories", tags=["repositories"])
async def add_repository(
    req: RepoAddRequest,
    background_tasks: BackgroundTasks,
    _user: dict = Depends(_get_current_user),
) -> dict[str, Any]:
    """Add a new repository and trigger background analysis."""
    # Token is optional — public repos work without it (60 req/hr rate limit)
    # Priority: request body token > env GITHUB_TOKEN > empty string (public repos only)
    token = req.token or getattr(settings, 'github_token', '') or ""

    # Derive repo_id
    url = req.url.strip().rstrip("/")
    try:
        if url.startswith("http"):
            parts = url.split("/")
            owner, repo = parts[-2], parts[-1].replace(".git", "")
        else:
            owner, _ = url.split("/", 1)
            repo = url.split("/")[-1].replace(".git", "")
        repo_id = f"{owner}/{repo}"
    except Exception:
        raise HTTPException(400, f"Cannot parse repository URL: {url}")

    if repo_id in _repo_registry:
        return {"repo_id": repo_id, "status": "already_tracked",
                "message": "Repository already tracked. Use re-scan to refresh."}

    # Placeholder while analysis runs
    _repo_registry[repo_id] = {
        "repo_id": repo_id,
        "repo_url": url,
        "owner": owner,
        "name": repo,
        "status": "analyzing",
        "analyzed_at": None,
        "issues": [],
    }

    background_tasks.add_task(_run_analysis, repo_id, url, token)
    return {"repo_id": repo_id, "status": "analysis_started",
            "message": f"Analysis of {repo_id} started. Refresh in 30-60 seconds."}


@app.post("/api/v1/repositories/{repo_id:path}/rescan", tags=["repositories"])
async def rescan_repository(
    repo_id: str,
    background_tasks: BackgroundTasks,
    _user: dict = Depends(_get_current_user),
) -> dict[str, Any]:
    if repo_id not in _repo_registry:
        raise HTTPException(404, "Repository not found")
    existing = _repo_registry[repo_id]
    token = settings.github_token if hasattr(settings, 'github_token') else ""
    _repo_registry[repo_id]["status"] = "analyzing"
    background_tasks.add_task(_run_analysis, repo_id, existing.get("repo_url", repo_id), token)
    return {"repo_id": repo_id, "status": "rescan_started"}


@app.get("/api/v1/repositories/{repo_id:path}/analysis", tags=["repositories"])
async def get_repo_analysis(
    repo_id: str,
    _user: dict = Depends(_get_current_user),
) -> dict[str, Any]:
    data = _repo_registry.get(repo_id)
    if not data:
        raise HTTPException(404, "Repository not found or not yet analyzed")
    return data


@app.get("/api/v1/repositories/{repo_id:path}/issues", tags=["repositories"])
async def get_repo_issues(
    repo_id: str,
    _user: dict = Depends(_get_current_user),
) -> dict[str, Any]:
    data = _repo_registry.get(repo_id)
    if not data:
        raise HTTPException(404, "Repository not found")
    issues = data.get("issues", [])
    # Attach feedback counts
    try:
        from integrations.github.repo_analyzer import feedback_store
        for issue in issues:
            iid = issue.get("issue_id", "")
            issue["feedback"] = feedback_store.get(iid, {"upvotes": 0, "downvotes": 0})
    except Exception:
        pass
    return {"repo_id": repo_id, "issues": issues, "total": len(issues)}


@app.post("/api/v1/repositories/{repo_id:path}/issues/{issue_id}/feedback", tags=["repositories"])
async def submit_issue_feedback(
    repo_id: str,
    issue_id: str,
    body: dict,
    _user: dict = Depends(_get_current_user),
) -> dict[str, Any]:
    """Upvote or downvote an issue suggestion (RL feedback loop). Supports both old in-memory and new MongoDB."""
    feedback_type = body.get("feedback")
    if feedback_type not in ("upvote", "downvote"):
        raise HTTPException(400, "feedback must be 'upvote' or 'downvote'")

    # Try MongoDB first (new path)
    if _mongo_db is not None and _MOTOR_OK:
        try:
            oid = ObjectId(issue_id)
            inc_field = "upvotes" if feedback_type == "upvote" else "downvotes"
            result = await _mongo_db["repo_errors"].find_one_and_update(
                {"_id": oid},
                {"$inc": {inc_field: 1}},
                return_document=True,
            )
            if result:
                # Store feedback record (ignore duplicate key errors)
                try:
                    await _mongo_db["error_feedback"].insert_one({
                        "error_id": oid,
                        "repo_id": repo_id,
                        "user_id": _user["user_id"],
                        "feedback": feedback_type,
                        "created_at": datetime.now(UTC),
                    })
                except Exception:
                    pass  # duplicate vote — ignore
                # Update RL weights
                await _update_rl_weights(_mongo_db, result["error_type"])
                counts = {"upvotes": result.get("upvotes", 0), "downvotes": result.get("downvotes", 0)}
                logger.info("mongo_error_feedback", repo=repo_id, error=issue_id, type=feedback_type)
                return {"issue_id": issue_id, "feedback": feedback_type, "counts": counts}
        except Exception as exc:
            logger.warning("mongo_feedback_fallback", error=str(exc))

    # Fallback: in-memory store (legacy issues from repo_analyzer.py)
    try:
        from integrations.github.repo_analyzer import feedback_store
        if issue_id not in feedback_store:
            feedback_store[issue_id] = {"upvotes": 0, "downvotes": 0}
        if feedback_type == "upvote":
            feedback_store[issue_id]["upvotes"] += 1
        else:
            feedback_store[issue_id]["downvotes"] += 1
        counts = feedback_store[issue_id]
    except Exception as exc:
        raise HTTPException(500, f"Feedback store error: {exc}")

    logger.info("issue_feedback", repo=repo_id, issue=issue_id, type=feedback_type)
    return {"issue_id": issue_id, "feedback": feedback_type, "counts": counts}


async def _update_rl_weights(db: Any, error_type: str) -> None:
    """Recalculate RL confidence threshold for an error_type and save to rl_weights."""
    try:
        # Aggregate votes across all errors of this type
        pipeline = [
            {"$match": {"error_type": error_type}},
            {"$group": {
                "_id": None,
                "total_upvotes": {"$sum": "$upvotes"},
                "total_downvotes": {"$sum": "$downvotes"},
            }},
        ]
        cursor = db["repo_errors"].aggregate(pipeline)
        agg = await cursor.to_list(length=1)
        if not agg:
            return
        total_upvotes = agg[0].get("total_upvotes", 0)
        total_downvotes = agg[0].get("total_downvotes", 0)
        total_votes = total_upvotes + total_downvotes
        if total_votes == 0:
            return
        upvote_ratio = total_upvotes / total_votes
        downvote_ratio = total_downvotes / total_votes
        new_threshold = 0.5 + (downvote_ratio - upvote_ratio) * 0.3
        new_threshold = max(0.2, min(0.8, new_threshold))
        await db["rl_weights"].update_one(
            {"error_type": error_type},
            {"$set": {
                "confidence_threshold": new_threshold,
                "upvote_count": total_upvotes,
                "downvote_count": total_downvotes,
                "last_updated": datetime.now(UTC),
            }},
            upsert=True,
        )
        logger.info("rl_weights_updated", error_type=error_type, threshold=new_threshold)
    except Exception as exc:
        logger.warning("rl_weights_update_error", error=str(exc))


# ── MongoDB Error Endpoints ─────────────────────────────────────────────────────

@app.get("/api/v1/repositories/{repo_id:path}/errors", tags=["repositories"])
async def get_repo_errors(
    repo_id: str,
    severity: Optional[str] = Query(default=None),
    error_type: Optional[str] = Query(default=None),
    file_path: Optional[str] = Query(default=None),
    resolved: Optional[bool] = Query(default=None),
    _user: dict = Depends(_get_current_user),
) -> dict[str, Any]:
    """Fetch all MongoDB-stored errors for this repository with optional filtering."""
    if _mongo_db is None:
        return {"errors": [], "total": 0, "info": "MongoDB not connected"}
    q: dict[str, Any] = {"repo_id": repo_id}
    if severity:
        q["severity"] = severity
    if error_type:
        q["error_type"] = error_type
    if file_path:
        q["file_path"] = file_path
    if resolved is not None:
        q["resolved"] = resolved
    errors = []
    async for doc in _mongo_db["repo_errors"].find(q).sort("severity", 1).limit(200):
        doc["_id"] = str(doc["_id"])
        doc["error_id"] = doc["_id"]
        errors.append(doc)
    return {"errors": errors, "total": len(errors), "repo_id": repo_id}


@app.get("/api/v1/repositories/{repo_id:path}/errors/{error_id}", tags=["repositories"])
async def get_repo_error(
    repo_id: str,
    error_id: str,
    _user: dict = Depends(_get_current_user),
) -> dict[str, Any]:
    """Fetch single error detail from MongoDB."""
    if _mongo_db is None:
        raise HTTPException(503, "MongoDB not connected")
    try:
        doc = await _mongo_db["repo_errors"].find_one({"_id": ObjectId(error_id), "repo_id": repo_id})
        if not doc:
            raise HTTPException(404, "Error not found")
        doc["_id"] = str(doc["_id"])
        doc["error_id"] = doc["_id"]
        return doc
    except (InvalidId, Exception) as exc:
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(400, f"Invalid error_id: {exc}")


@app.post("/api/v1/repositories/{repo_id:path}/errors/{error_id}/feedback", tags=["repositories"])
async def submit_error_feedback(
    repo_id: str,
    error_id: str,
    body: dict,
    _user: dict = Depends(_get_current_user),
) -> dict[str, Any]:
    """MongoDB-specific upvote/downvote with RL weight update."""
    feedback_type = body.get("feedback")
    if feedback_type not in ("upvote", "downvote"):
        raise HTTPException(400, "feedback must be 'upvote' or 'downvote'")
    if _mongo_db is None:
        raise HTTPException(503, "MongoDB not connected")
    try:
        oid = ObjectId(error_id)
    except Exception:
        raise HTTPException(400, "Invalid error_id format")
    inc_field = "upvotes" if feedback_type == "upvote" else "downvotes"
    doc = await _mongo_db["repo_errors"].find_one_and_update(
        {"_id": oid, "repo_id": repo_id},
        {"$inc": {inc_field: 1}},
        return_document=True,
    )
    if not doc:
        raise HTTPException(404, "Error not found")
    try:
        await _mongo_db["error_feedback"].insert_one({
            "error_id": oid,
            "repo_id": repo_id,
            "user_id": _user["user_id"],
            "feedback": feedback_type,
            "created_at": datetime.now(UTC),
        })
    except Exception:
        pass  # duplicate vote
    await _update_rl_weights(_mongo_db, doc["error_type"])
    doc["_id"] = str(doc["_id"])
    new_threshold = None
    rl = await _mongo_db["rl_weights"].find_one({"error_type": doc["error_type"]})
    if rl:
        new_threshold = rl.get("confidence_threshold")
    return {
        "error_id": error_id,
        "feedback": feedback_type,
        "upvotes": doc.get("upvotes", 0),
        "downvotes": doc.get("downvotes", 0),
        "new_threshold": new_threshold,
    }


@app.put("/api/v1/repositories/{repo_id:path}/errors/{error_id}/resolve", tags=["repositories"])
async def resolve_error(
    repo_id: str,
    error_id: str,
    _user: dict = Depends(_get_current_user),
) -> dict[str, Any]:
    """Mark a MongoDB error as resolved."""
    if _mongo_db is None:
        raise HTTPException(503, "MongoDB not connected")
    try:
        result = await _mongo_db["repo_errors"].update_one(
            {"_id": ObjectId(error_id), "repo_id": repo_id},
            {"$set": {"resolved": True, "resolved_at": datetime.now(UTC),
                      "resolved_by": _user["user_id"]}},
        )
        if result.matched_count == 0:
            raise HTTPException(404, "Error not found")
        return {"error_id": error_id, "resolved": True}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, f"Invalid error_id: {exc}")


@app.get("/api/v1/repositories/{repo_id:path}/issues/{issue_id}/feedback/counts", tags=["repositories"])
async def get_issue_feedback_counts(
    repo_id: str,
    issue_id: str,
    _user: dict = Depends(_get_current_user),
) -> dict[str, Any]:
    try:
        from integrations.github.repo_analyzer import feedback_store
        counts = feedback_store.get(issue_id, {"upvotes": 0, "downvotes": 0})
    except Exception:
        counts = {"upvotes": 0, "downvotes": 0}
    return {"issue_id": issue_id, "counts": counts}


@app.get("/api/v1/repositories/{repo_id:path}/logs", tags=["repositories"])
async def get_repo_logs(
    repo_id: str,
    _user: dict = Depends(_get_current_user),
) -> dict[str, Any]:
    """Return GitHub Actions logs if available, otherwise an empty-state message."""
    data = _repo_registry.get(repo_id)
    if not data:
        raise HTTPException(404, "Repository not found")

    token = settings.github_token if hasattr(settings, 'github_token') else ""
    if not token:
        return {
            "logs": [],
            "empty_state": True,
            "message": "No runtime logs available. Install the NeuralOps SDK to see live logs. Showing GitHub Actions status instead.",
        }

    owner = data.get("owner", "")
    repo = data.get("name", "")

    import httpx
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/actions/runs?per_page=5",
                headers={"Authorization": f"token {token}",
                         "Accept": "application/vnd.github.v3+json"},
            )
            if resp.status_code != 200:
                return {"logs": [], "empty_state": True,
                        "message": "No GitHub Actions workflows found in this repository."}

            runs = resp.json().get("workflow_runs", [])
            log_entries = []
            for run in runs:
                log_entries.append({
                    "timestamp": run.get("created_at"),
                    "level": "ERROR" if run.get("conclusion") == "failure" else "INFO",
                    "message": f"[{run.get('name')}] {run.get('event')} → {run.get('conclusion', 'in_progress')}",
                    "source": "github_actions",
                    "run_id": run.get("id"),
                    "url": run.get("html_url"),
                })
        return {"logs": log_entries, "source": "github_actions", "total": len(log_entries)}
    except Exception as exc:
        return {"logs": [], "empty_state": True,
                "message": f"Could not fetch GitHub Actions logs: {exc}"}


# ── Background tasks ───────────────────────────────────────────────────────────

async def _run_analysis(repo_id: str, repo_url: str, token: str) -> None:
    """Background task: run full repo analysis and store result."""
    try:
        from integrations.github.repo_analyzer import GitHubRepoAnalyzer
        from shared.llm import llm_service
        try:
            llm_provider = llm_service
        except Exception:
            llm_provider = None

        ollama_url = settings.ollama_base_url
        analyzer = GitHubRepoAnalyzer(token=token, ollama_url=ollama_url,
                                       gemini_provider=llm_provider)
        result = await analyzer.analyze(repo_url)
        _repo_registry[repo_id] = result
        logger.info("repo_analysis_complete", repo=repo_id,
                    files=result.get("total_files"),
                    issues=result.get("issues_found"))
    except Exception as exc:
        logger.error("repo_analysis_failed", repo=repo_id, error=str(exc))
        if repo_id in _repo_registry:
            _repo_registry[repo_id]["status"] = "error"
            _repo_registry[repo_id]["error"] = str(exc)


async def _repo_poll_loop() -> None:
    """Persistent background task: poll repos every 5 minutes for connection stability."""
    await asyncio.sleep(30)  # Give startup time
    while True:
        try:
            token = settings.github_token if hasattr(settings, 'github_token') else ""
            if not token:
                await asyncio.sleep(300)
                continue

            import httpx
            for repo_id, data in list(_repo_registry.items()):
                if data.get("status") == "analyzing":
                    continue
                owner = data.get("owner", "")
                repo = data.get("name", "")
                if not owner or not repo:
                    continue
                try:
                    async with httpx.AsyncClient(timeout=10) as client:
                        resp = await client.get(
                            f"https://api.github.com/repos/{owner}/{repo}",
                            headers={"Authorization": f"token {token}",
                                     "Accept": "application/vnd.github.v3+json"},
                        )
                    if resp.status_code == 200:
                        meta = resp.json()
                        data["last_commit"] = meta.get("pushed_at")
                        data["stars"] = meta.get("stargazers_count", data.get("stars", 0))
                        data["status"] = "active"
                        _repo_poll_failures[repo_id] = 0
                    else:
                        _repo_poll_failures[repo_id] = _repo_poll_failures.get(repo_id, 0) + 1
                        if _repo_poll_failures[repo_id] >= 3:
                            data["status"] = "error"
                except Exception as exc:
                    _repo_poll_failures[repo_id] = _repo_poll_failures.get(repo_id, 0) + 1
                    logger.warning("repo_poll_failed", repo=repo_id, error=str(exc))

        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("repo_poll_loop_error", error=str(exc))

        await asyncio.sleep(300)  # 5-minute poll interval


# ── Incidents ─────────────────────────────────────────────────────────────────

@app.get("/api/v1/incidents", tags=["incidents"])
async def list_incidents(
    status: str | None = None,
    severity: str | None = None,
    project_id: str | None = Query(default=None),
    limit: int = 50,
    offset: int = 0,
    _user: dict = Depends(_get_current_user),
) -> dict[str, Any]:
    if _sf is None:
        return {"incidents": [], "total": 0, "limit": limit, "offset": offset,
                "info": "Database not connected. Start PostgreSQL to see real incidents."}
    conditions = ["1=1"]
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if status:
        conditions.append("status = :status"); params["status"] = status
    if severity:
        conditions.append("severity = :severity"); params["severity"] = severity
    if project_id:
        conditions.append("(repo_id = :project_id OR repo_id::text = :project_id)"); params["project_id"] = project_id
    where = " AND ".join(conditions)
    async with _sf() as session:
        res = await session.execute(
            text(f"SELECT * FROM incidents WHERE {where} ORDER BY detected_at DESC LIMIT :limit OFFSET :offset"),
            params,
        )
        rows = [dict(r) for r in res.mappings()]
        count_res = await session.execute(
            text(f"SELECT COUNT(*) FROM incidents WHERE {where}"),
            {k: v for k, v in params.items() if k not in ("limit", "offset")},
        )
        total = count_res.scalar()
    return {"incidents": rows, "total": total, "limit": limit, "offset": offset}


@app.get("/api/v1/incidents/{incident_id}", tags=["incidents"])
async def get_incident(
    incident_id: str, _user: dict = Depends(_get_current_user)
) -> dict[str, Any]:
    if _sf is None:
        raise HTTPException(503, "Database not connected")
    async with _sf() as session:
        res = await session.execute(
            text("SELECT * FROM incidents WHERE incident_id = :iid"), {"iid": incident_id}
        )
        row = res.mappings().first()
    if not row:
        raise HTTPException(404, "Incident not found")
    return dict(row)


@app.patch("/api/v1/incidents/{incident_id}/status", tags=["incidents"])
async def update_incident_status(
    incident_id: str, body: dict, _user: dict = Depends(_get_current_user)
) -> dict[str, str]:
    import httpx
    new_status = body.get("status")
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.patch(
                f"http://orchestrator:8020/incidents/{incident_id}/status",
                json={"status": new_status, "resolved_by": _user["user_id"]},
            )
            resp.raise_for_status()
        except Exception:
            pass
    return {"status": "updated"}


@app.post("/api/v1/incidents/{incident_id}/feedback", tags=["incidents"])
async def submit_incident_feedback(
    incident_id: str, body: dict, _user: dict = Depends(_get_current_user)
) -> dict[str, str]:
    return {"status": "feedback recorded", "incident_id": incident_id}


# ── Anomalies ─────────────────────────────────────────────────────────────────

@app.get("/api/v1/anomalies", tags=["anomalies"])
async def list_anomalies(
    service: str | None = None,
    project_id: str | None = Query(default=None),
    limit: int = 100,
    _user: dict = Depends(_get_current_user),
) -> dict[str, Any]:
    if _redis is None:
        return {"anomalies": [], "total": 0,
                "info": "Redis not connected. Start Redis to see real anomalies."}
    raw = await _redis.lrange("neuralops:dashboard:top_anomalies", 0, limit - 1)
    anomalies = [json.loads(r) for r in raw]
    if service:
        anomalies = [a for a in anomalies if a.get("service_name") == service]
    if project_id:
        anomalies = [a for a in anomalies if str(a.get("repo_id", "")) == project_id
                     or a.get("project_id") == project_id]
    return {"anomalies": anomalies, "total": len(anomalies)}


# ── RCA ────────────────────────────────────────────────────────────────────────

@app.get("/api/v1/incidents/{incident_id}/rca", tags=["rca"])
async def get_rca(
    incident_id: str, _user: dict = Depends(_get_current_user)
) -> dict[str, Any]:
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"http://rca_engine:8040/rca/{incident_id}")
            if resp.status_code == 404:
                raise HTTPException(404, "RCA not found")
            resp.raise_for_status()
            return resp.json()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "RCA engine not available")


# ── Actions ────────────────────────────────────────────────────────────────────

@app.post("/api/v1/actions", tags=["actions"])
async def execute_action(
    action: ActionRequest, _user: dict = Depends(_get_current_user)
) -> dict[str, Any]:
    if _user["role"] not in ("operator", "admin"):
        raise HTTPException(403, "Insufficient permissions")
    action.requested_by = _user["user_id"]
    import httpx
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "http://action_executor:8030/execute",
                json=action.model_dump(mode="json"),
            )
            resp.raise_for_status()
            return resp.json()
    except Exception:
        raise HTTPException(503, "Action executor not available")


@app.get("/api/v1/actions/audit", tags=["actions"])
async def list_audit(
    incident_id: str | None = None,
    limit: int = 50,
    _user: dict = Depends(_get_current_user),
) -> dict[str, Any]:
    if _sf is None:
        return {"audit": []}
    params: dict[str, Any] = {"limit": limit}
    where = "1=1"
    if incident_id:
        where += " AND incident_id = :iid"
        params["iid"] = incident_id
    async with _sf() as session:
        res = await session.execute(
            text(f"SELECT * FROM action_audit WHERE {where} ORDER BY created_at DESC LIMIT :limit"),
            params,
        )
        rows = [dict(r) for r in res.mappings()]
    return {"audit": rows}


# ── Dashboard summary ──────────────────────────────────────────────────────────

@app.get("/api/v1/dashboard/summary", tags=["dashboard"])
async def dashboard_summary(_user: dict = Depends(_get_current_user)) -> dict[str, Any]:
    """Dashboard summary — real DB data when available, empty structure otherwise."""
    summary: dict[str, Any] = {
        "incidents_by_status": {},
        "active_incidents_by_severity": {},
        "avg_mttr_7d_minutes": None,
        "top_anomalies": [],
        "generated_at": datetime.now(UTC).isoformat(),
    }

    if _sf is not None:
        try:
            async with _sf() as session:
                inc_counts = await session.execute(
                    text("""
                        SELECT status, COUNT(*) as cnt FROM incidents
                        WHERE detected_at >= NOW() - INTERVAL '24 hours'
                        GROUP BY status
                    """)
                )
                sev_counts = await session.execute(
                    text("""
                        SELECT severity, COUNT(*) as cnt FROM incidents
                        WHERE status != 'resolved' AND detected_at >= NOW() - INTERVAL '24 hours'
                        GROUP BY severity
                    """)
                )
                mttr_result = await session.execute(
                    text("SELECT AVG(mttr_minutes) FROM incidents WHERE resolved_at >= NOW() - INTERVAL '7 days'")
                )
            summary["incidents_by_status"] = {r["status"]: r["cnt"] for r in inc_counts.mappings()}
            summary["active_incidents_by_severity"] = {r["severity"]: r["cnt"] for r in sev_counts.mappings()}
            avg_mttr = mttr_result.scalar()
            summary["avg_mttr_7d_minutes"] = round(float(avg_mttr), 1) if avg_mttr else None
        except Exception as exc:
            logger.warning("dashboard_summary_db_error", error=str(exc))

    if _redis is not None:
        try:
            top_raw = await _redis.lrange("neuralops:dashboard:top_anomalies", 0, 4)
            summary["top_anomalies"] = [json.loads(r) for r in top_raw]
        except Exception:
            pass

    return summary


# ── Chatbot SSE ────────────────────────────────────────────────────────────────

async def _do_chat_stream(req: ChatRequest, _user: dict) -> StreamingResponse:
    if _chatbot is None:
        raise HTTPException(503, "Chatbot service not initialized")

    session_id = req.session_id or str(uuid.uuid4())
    session = _chatbot.get_or_create_session(session_id, _user["user_id"])
    if req.context_incident_id:
        session.context_incident_id = req.context_incident_id

    async def event_stream() -> AsyncGenerator[str, None]:
        yield f"data: {{\"session_id\": \"{session_id}\"}}\n\n"
        async for token in _chatbot.chat(session, req.message):
            escaped = token.replace('"', '\\"').replace("\n", "\\n")
            yield f"data: {{\"token\": \"{escaped}\"}}\n\n"
        yield "data: {\"done\": true}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Session-Id": session_id,
        },
    )


@app.post("/api/v1/chat", tags=["chatbot"])
async def chat_stream(
    req: ChatRequest, _user: dict = Depends(_get_current_user)
) -> StreamingResponse:
    return await _do_chat_stream(req, _user)


@app.post("/api/v1/chatbot/stream", tags=["chatbot"])
async def chatbot_stream(
    req: ChatRequest, _user: dict = Depends(_get_current_user)
) -> StreamingResponse:
    return await _do_chat_stream(req, _user)


@app.post("/api/v1/chatbot/message", tags=["chatbot"])
async def chatbot_message_rest(
    req: ChatRequest, _user: dict = Depends(_get_current_user)
) -> dict[str, Any]:
    """REST fallback for chatbot — non-streaming. Used when SSE/WebSocket unavailable."""
    if _chatbot is None:
        raise HTTPException(503, "Chatbot service not initialized")
    session_id = req.session_id or str(uuid.uuid4())
    session = _chatbot.get_or_create_session(session_id, _user["user_id"])
    if req.context_incident_id:
        session.context_incident_id = req.context_incident_id
    full_response = ""
    try:
        async for token in _chatbot.chat(session, req.message):
            full_response += token
    except Exception as exc:
        raise HTTPException(500, f"Chat error: {exc}")
    return {"session_id": session_id, "message": full_response, "done": True}


@app.get("/api/v1/chat/{session_id}/history", tags=["chatbot"])
async def chat_history(
    session_id: str, _user: dict = Depends(_get_current_user)
) -> dict[str, Any]:
    if _chatbot is None:
        raise HTTPException(503)
    history = await _chatbot.get_chat_history(session_id)
    return {"session_id": session_id, "messages": history}


@app.post("/api/v1/chatbot/feedback", tags=["chatbot"])
async def chatbot_feedback(
    body: dict, _user: dict = Depends(_get_current_user)
) -> dict[str, str]:
    logger.info("chatbot_feedback", session=body.get("session_id"),
                rating=body.get("rating"))
    return {"status": "recorded"}


# ── WebSocket — real-time incident feed ────────────────────────────────────────

@app.websocket("/ws/incidents")
async def ws_incidents(ws: WebSocket) -> None:
    await ws.accept()
    _ws_connections.setdefault("incidents", []).append(ws)
    try:
        while True:
            if _redis is not None:
                try:
                    messages = await _redis.xread(
                        {settings.redis_stream_incidents: "$"},
                        count=10, block=2000,
                    )
                    for _stream, events in (messages or []):
                        for _, fields in events:
                            payload = json.loads(fields.get("payload", "{}"))
                            await ws.send_json(payload)
                except Exception:
                    await asyncio.sleep(2)
            else:
                await asyncio.sleep(5)
    except WebSocketDisconnect:
        pass
    finally:
        conns = _ws_connections.get("incidents", [])
        if ws in conns:
            conns.remove(ws)


@app.websocket("/ws/metrics")
async def ws_metrics(ws: WebSocket) -> None:
    """Push real-time system metrics every 10 seconds."""
    await ws.accept()
    try:
        from modules.ingestion.collectors.system_metrics import get_latest_metrics
        while True:
            try:
                sample = get_latest_metrics()
                await ws.send_json({"type": "metrics_update", "data": sample})
            except Exception:
                pass
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        pass


# ── RL Stats stub ──────────────────────────────────────────────────────────────

@app.get("/api/v1/rl/stats", tags=["rl"])
async def get_rl_stats(_user: dict = Depends(_get_current_user)) -> dict[str, Any]:
    try:
        from integrations.github.repo_analyzer import feedback_store
        total_upvotes = sum(v["upvotes"] for v in feedback_store.values())
        total_downvotes = sum(v["downvotes"] for v in feedback_store.values())
        total = total_upvotes + total_downvotes
        return {
            "total_feedback": total,
            "total_upvotes": total_upvotes,
            "total_downvotes": total_downvotes,
            "acceptance_rate": round(total_upvotes / total, 2) if total > 0 else 0.0,
            "suggestions_tracked": len(feedback_store),
        }
    except Exception:
        return {"total_feedback": 0, "total_upvotes": 0, "total_downvotes": 0,
                "acceptance_rate": 0.0, "suggestions_tracked": 0}



# ── MongoDB Error CRUD Endpoints ───────────────────────────────────────────────

@app.get("/api/v1/repositories/{repo_id}/errors", tags=["errors"])
async def get_repo_errors(
    repo_id: str,
    severity: Optional[str] = Query(default=None),
    error_type: Optional[str] = Query(default=None),
    file_path: Optional[str] = Query(default=None),
    is_resolved: Optional[bool] = Query(default=None),
    limit: int = Query(default=200, le=500),
    skip: int = Query(default=0),
    _user: dict = Depends(_get_current_user),
) -> dict:
    """Fetch all errors for a repo from MongoDB with optional filters."""
    from modules.api.services.error_service import get_errors_for_repo
    return await get_errors_for_repo(
        _mongo_db, repo_id,
        severity=severity, error_type=error_type,
        file_path=file_path, is_resolved=is_resolved,
        limit=limit, skip=skip,
    )


@app.get("/api/v1/repositories/{repo_id}/errors/{error_id}", tags=["errors"])
async def get_single_repo_error(
    repo_id: str,
    error_id: str,
    _user: dict = Depends(_get_current_user),
) -> dict:
    """Fetch a single error document by ObjectId string."""
    from modules.api.services.error_service import get_single_error
    doc = await get_single_error(_mongo_db, repo_id, error_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Error not found")
    return doc


class FeedbackRequest(BaseModel):
    feedback: str  # "upvote" or "downvote"


@app.post("/api/v1/repositories/{repo_id}/errors/{error_id}/feedback", tags=["errors"])
async def submit_error_feedback(
    repo_id: str,
    error_id: str,
    body: FeedbackRequest,
    user: dict = Depends(_get_current_user),
) -> dict:
    """Record upvote/downvote feedback and update RL confidence weights."""
    if body.feedback not in ("upvote", "downvote"):
        raise HTTPException(status_code=422, detail="feedback must be 'upvote' or 'downvote'")
    from modules.api.services.error_service import (
        get_single_error,
        process_feedback,
        update_rl_weights,
    )
    # Get error type before processing feedback (needed for RL update)
    err = await get_single_error(_mongo_db, repo_id, error_id)
    if err is None:
        raise HTTPException(status_code=404, detail="Error not found")

    result = await process_feedback(
        _mongo_db, repo_id, error_id, user["user_id"], body.feedback
    )
    if result.get("already_voted"):
        raise HTTPException(status_code=409, detail="You have already voted on this error")
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    # Update RL weights for this error type
    new_threshold = await update_rl_weights(_mongo_db, err.get("error_type", "unknown"))
    result["new_threshold"] = new_threshold
    return result


@app.put("/api/v1/repositories/{repo_id}/errors/{error_id}/resolve", tags=["errors"])
async def resolve_repo_error(
    repo_id: str,
    error_id: str,
    _user: dict = Depends(_get_current_user),
) -> dict:
    """Mark an error as resolved in MongoDB."""
    from modules.api.services.error_service import resolve_error
    success = await resolve_error(_mongo_db, repo_id, error_id)
    if not success:
        raise HTTPException(status_code=404, detail="Error not found or already resolved")
    return {"resolved": True, "error_id": error_id}


# ── Health Check Endpoints ────────────────────────────────────────────────────

@app.get("/api/v1/health/phi3", tags=["health"])
async def check_phi3_health() -> dict:
    """
    Full Phi-3 / Ollama health check.
    Checks: Ollama reachable → phi3 model installed → quick inference test.
    """
    import time as _time
    result: dict[str, Any] = {
        "ollama_reachable": False,
        "model_installed": False,
        "model_ready": False,
        "model_name": None,
        "response_time_ms": None,
        "error": None,
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            resp.raise_for_status()
            result["ollama_reachable"] = True
            models = resp.json().get("models", [])
            phi3_models = [m for m in models if "phi3" in m.get("name", "").lower()]
            if not phi3_models:
                result["error"] = (
                    f"phi3 model not installed. "
                    f"Run: docker exec neuralops-ollama ollama pull phi3:mini"
                )
                return result
            result["model_installed"] = True
            result["model_name"] = phi3_models[0]["name"]
            # Quick inference test
            t0 = _time.monotonic()
            test = await client.post(
                f"{settings.ollama_base_url}/api/generate",
                json={
                    "model": result["model_name"],
                    "prompt": "Reply with the single word: OK",
                    "stream": False,
                    "options": {"temperature": 0.0, "num_predict": 5},
                },
                timeout=30.0,
            )
            elapsed_ms = round((_time.monotonic() - t0) * 1000, 1)
            if test.status_code == 200 and test.json().get("response"):
                result["model_ready"] = True
                result["response_time_ms"] = elapsed_ms
            else:
                result["error"] = f"Inference test failed: HTTP {test.status_code}"
    except httpx.ConnectError:
        result["error"] = f"Cannot reach Ollama at {settings.ollama_base_url}"
    except Exception as exc:
        result["error"] = str(exc)
    return result


@app.get("/api/v1/health/gemini", tags=["health"])
async def check_gemini_health_compat() -> dict:
    """Backward-compat alias for /api/v1/health/llm."""
    from shared.llm import llm_service
    result = await llm_service.health_check()
    or_info = result.get("openrouter", {})
    return {
        "connected": or_info.get("available", False),
        "provider": result.get("active_model", "none"),
        "model": or_info.get("model"),
        "error": or_info.get("error"),
    }


@app.get("/api/v1/chatbot/health", tags=["chatbot"])
async def chatbot_health_compat() -> dict:
    """Reports availability of OpenRouter and Phi-3 and the active model."""
    from shared.llm import llm_service
    return await llm_service.health_check()


# ── Chatbot REST fallback (registered directly on app for compatibility) ───────

class _ChatRequest(BaseModel):
    message: str
    project_id: Optional[str] = None
    session_id: Optional[str] = None


@app.post("/api/v1/chatbot/message", tags=["chatbot"])
async def chatbot_message_rest(
    body: _ChatRequest,
    _user: dict = Depends(_get_current_user),
) -> dict:
    """REST fallback when WebSocket cannot be established."""
    from modules.api.routers.chatbot import (
        build_chat_context, build_prompt, format_history,
        get_conversation_history, save_conversation_turn,
        CHATBOT_SYSTEM_PROMPT,
    )
    from shared.llm import llm_service

    context = await build_chat_context(
        body.message,
        body.project_id,
        _user.get("user_id", "rest"),
        mongo_db=_mongo_db,
        redis_client=_redis,
    )
    session_id = body.session_id or "rest-anon"
    history = await get_conversation_history(session_id, _redis)
    history_text = format_history(history)
    data_prompt = build_prompt(body.message, context)
    final_prompt = f"{history_text}\n\n{data_prompt}" if history_text else data_prompt

    try:
        response_text = await llm_service.generate(final_prompt, CHATBOT_SYSTEM_PROMPT)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"LLM service unavailable: {exc}")

    model_used = llm_service.model if llm_service.openrouter_available else "phi3:mini"
    await save_conversation_turn(session_id, body.message, response_text, _redis)
    return {"response": response_text, "model_used": model_used, "intent": context.get("intent")}


@app.get("/api/v1/settings/rl-stats", tags=["settings"])
async def get_rl_stats_from_mongo(_user: dict = Depends(_get_current_user)) -> dict:
    """Returns aggregated RL model performance stats from MongoDB."""
    if _mongo_db is None:
        return {"accuracy": 0.0, "total": 0, "last_trained": None}
    try:
        pipeline = [{"$group": {
            "_id": None,
            "total_upvotes": {"$sum": "$upvotes"},
            "total_downvotes": {"$sum": "$downvotes"},
        }}]
        async for agg in _mongo_db["repo_errors"].aggregate(pipeline):
            up = agg.get("total_upvotes", 0)
            down = agg.get("total_downvotes", 0)
            total = up + down
            accuracy = round(up / total, 3) if total > 0 else 0.0
            return {"accuracy": accuracy, "total": total, "last_trained": None}
        return {"accuracy": 0.0, "total": 0, "last_trained": None}
    except Exception:
        return {"accuracy": 0.0, "total": 0, "last_trained": None}


# ── Settings stubs ─────────────────────────────────────────────────────────────

@app.get("/api/v1/settings/integrations", tags=["settings"])
async def get_integrations(_user: dict = Depends(_get_current_user)) -> dict[str, Any]:
    return {
        "openrouter": {"enabled": bool(settings.openrouter_api_key), "key_set": bool(settings.openrouter_api_key), "model": settings.openrouter_model},
        "github": {"enabled": True, "token_set": bool(getattr(settings, 'github_token', ''))},
        "slack": {"enabled": getattr(settings, 'slack_enabled', False)},
        "pagerduty": {"enabled": getattr(settings, 'pagerduty_enabled', False)},
    }


# ── Website URL management ─────────────────────────────────────────────────────

class WebsiteUrlRequest(BaseModel):
    website_url: str
    is_live_monitoring_enabled: bool = True


@app.put("/api/v1/repositories/{repo_id}/website-url", tags=["repositories"])
async def set_website_url(
    repo_id: str,
    req: WebsiteUrlRequest,
    _user: dict = Depends(_get_current_user),
) -> dict[str, Any]:
    """Set or update the monitored website URL for a repository."""
    if _sf is None:
        raise HTTPException(503, "Database not available")
    try:
        async with _sf() as session:
            # Upsert: if repo doesn't exist in DB create a minimal record
            await session.execute(
                text(
                    "INSERT INTO repositories (id, name, owner, website_url, is_live_monitoring_enabled) "
                    "VALUES (:id, :id, 'user', :url, :live) "
                    "ON CONFLICT (id) DO UPDATE SET "
                    "  website_url = EXCLUDED.website_url, "
                    "  is_live_monitoring_enabled = EXCLUDED.is_live_monitoring_enabled, "
                    "  updated_at = NOW()"
                ),
                {"id": repo_id, "url": req.website_url, "live": req.is_live_monitoring_enabled},
            )
            await session.commit()
    except Exception as exc:
        raise HTTPException(500, f"Failed to save website URL: {exc}")
    return {"repo_id": repo_id, "website_url": req.website_url, "is_live_monitoring_enabled": req.is_live_monitoring_enabled}


@app.get("/api/v1/repositories/{repo_id}/website-checks", tags=["repositories"])
async def get_website_checks(
    repo_id: str,
    limit: int = Query(default=100, le=500),
    _user: dict = Depends(_get_current_user),
) -> dict[str, Any]:
    """Return recent HTTP status check history for a repository's website URL."""
    if _sf is None:
        return {"checks": [], "repo_id": repo_id}
    try:
        async with _sf() as session:
            result = await session.execute(
                text(
                    "SELECT id, url, status_code, response_time_ms, is_up, checked_at "
                    "FROM website_checks WHERE repo_id = :repo_id "
                    "ORDER BY checked_at DESC LIMIT :limit"
                ),
                {"repo_id": repo_id, "limit": limit},
            )
            rows = result.mappings().all()
        return {
            "repo_id": repo_id,
            "checks": [
                {
                    "id": str(r["id"]),
                    "url": r["url"],
                    "status_code": r["status_code"],
                    "response_time_ms": r["response_time_ms"],
                    "is_up": r["is_up"],
                    "checked_at": r["checked_at"].isoformat() if r["checked_at"] else None,
                }
                for r in rows
            ],
        }
    except Exception as exc:
        logger.warning("website_checks_fetch_failed", error=str(exc))
        return {"checks": [], "repo_id": repo_id}


# ── Incident History ───────────────────────────────────────────────────────────

@app.get("/api/v1/incidents/history", tags=["incidents"])
async def get_incident_history(
    project_id: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    from_date: Optional[str] = Query(default=None),
    to_date: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25, le=100),
    sort_by: str = Query(default="detected_at"),
    sort_order: str = Query(default="desc"),
    _user: dict = Depends(_get_current_user),
) -> dict[str, Any]:
    """Return paginated incident history with full filtering and sorting."""
    if _sf is None:
        return {"incidents": [], "total_count": 0, "page": page, "per_page": per_page}

    allowed_sort = {"detected_at", "severity", "status", "primary_service", "mttr_minutes", "resolved_at", "title"}
    if sort_by not in allowed_sort:
        sort_by = "detected_at"
    sort_order_sql = "DESC" if sort_order.lower() == "desc" else "ASC"

    conditions = []
    params: dict = {}

    if project_id:
        conditions.append("repo_id = :project_id")
        params["project_id"] = project_id
    if severity:
        conditions.append("severity = :severity")
        params["severity"] = severity
    if status:
        conditions.append("status = :status")
        params["status"] = status
    if from_date:
        conditions.append("detected_at >= :from_date")
        params["from_date"] = from_date
    if to_date:
        conditions.append("detected_at <= :to_date")
        params["to_date"] = to_date
    if search:
        conditions.append("(title ILIKE :search OR root_cause ILIKE :search OR description ILIKE :search)")
        params["search"] = f"%{search}%"

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    offset = (page - 1) * per_page

    try:
        async with _sf() as session:
            count_result = await session.execute(
                text(f"SELECT COUNT(*) FROM incidents {where}"), params
            )
            total_count = count_result.scalar() or 0

            rows_result = await session.execute(
                text(
                    f"SELECT incident_id, title, severity, status, detected_at, resolved_at, "
                    f"       mttr_minutes, primary_service, affected_services, root_cause, "
                    f"       remediation_steps, description, environment, cloud_provider, "
                    f"       peak_anomaly_score, ml_confidence, repo_id "
                    f"FROM incidents {where} "
                    f"ORDER BY {sort_by} {sort_order_sql} "
                    f"LIMIT :limit OFFSET :offset"
                ),
                {**params, "limit": per_page, "offset": offset},
            )
            rows = rows_result.mappings().all()

        incidents = []
        for r in rows:
            affected = r["affected_services"]
            if isinstance(affected, str):
                import json as _json
                try: affected = _json.loads(affected)
                except Exception: affected = []
            remediation = r["remediation_steps"]
            if isinstance(remediation, str):
                import json as _json
                try: remediation = _json.loads(remediation)
                except Exception: remediation = []

            incidents.append({
                "incident_id": str(r["incident_id"]),
                "title": r["title"],
                "severity": r["severity"],
                "status": r["status"],
                "detected_at": r["detected_at"].isoformat() if r["detected_at"] else None,
                "resolved_at": r["resolved_at"].isoformat() if r["resolved_at"] else None,
                "mttr_minutes": r["mttr_minutes"],
                "primary_service": r["primary_service"],
                "affected_services": affected,
                "root_cause": r["root_cause"],
                "remediation_steps": remediation,
                "description": r["description"],
                "environment": r["environment"],
                "cloud_provider": r["cloud_provider"],
                "peak_anomaly_score": r["peak_anomaly_score"],
                "ml_confidence": r["ml_confidence"],
                "repo_id": str(r["repo_id"]) if r["repo_id"] else None,
            })

        return {
            "incidents": incidents,
            "total_count": total_count,
            "page": page,
            "per_page": per_page,
            "total_pages": (total_count + per_page - 1) // per_page,
        }
    except Exception as exc:
        logger.warning("incident_history_failed", error=str(exc))
        return {"incidents": [], "total_count": 0, "page": page, "per_page": per_page, "total_pages": 0}


# ── Entry point ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "modules.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.api_log_level,
        reload=False,
    )
