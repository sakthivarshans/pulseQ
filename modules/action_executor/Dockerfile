FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl gcc build-essential libpq-dev ca-certificates && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir --trusted-host pypi.org --trusted-host files.pythonhosted.org uv
ENV UV_NATIVE_TLS=1
WORKDIR /app
COPY pyproject.toml uv.lock* README.md ./
RUN uv sync --no-dev --no-install-project --native-tls
COPY . .
EXPOSE 8050
CMD ["uv", "run", "uvicorn", "modules.action_executor.main:app", "--host", "0.0.0.0", "--port", "8050"]
