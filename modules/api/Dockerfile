FROM python:3.11-slim

# ── System dependencies ────────────────────────────────────────────────────────
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    g++ \
    libpq-dev \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ── Install uv (fast Python package manager) ──────────────────────────────────
RUN pip install --no-cache-dir uv
ENV UV_NATIVE_TLS=1

# ── Non-root user ──────────────────────────────────────────────────────────────
RUN useradd -m -u 1000 -s /bin/bash neuralops

WORKDIR /app

# ── Install Python dependencies ───────────────────────────────────────────────
# Copy dependency files first (better layer caching — only reinstalls when deps change)
COPY pyproject.toml uv.lock* README.md ./
RUN uv sync --no-dev --no-install-project --native-tls

# ── Copy application source ───────────────────────────────────────────────────
COPY . .

# ── Create model directories and set ownership ────────────────────────────────
RUN mkdir -p /app/models /app/training/data \
    && chown -R neuralops:neuralops /app

USER neuralops

EXPOSE 8080

# ── Health check ──────────────────────────────────────────────────────────────
HEALTHCHECK --interval=10s --timeout=5s --retries=15 --start-period=45s \
    CMD curl -f http://localhost:8080/health || exit 1

CMD ["uv", "run", "uvicorn", "modules.api.main:app", \
    "--host", "0.0.0.0", \
    "--port", "8080", \
    "--loop", "asyncio", \
    "--workers", "1"]
