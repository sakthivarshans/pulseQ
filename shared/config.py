"""
shared/config.py
────────────────
Central Pydantic Settings for NeuralOps.
All configuration is loaded from environment variables / .env file.
No module ever reads os.environ directly — always uses this Settings object.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database ────────────────────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://neuralops:neuralops123@postgres:5432/neuralops",
        description="Async PostgreSQL DSN"
    )
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "neuralops"
    postgres_user: str = "neuralops"
    postgres_password: str = Field(default="neuralops123", description="PostgreSQL password")

    # ── Redis ────────────────────────────────────────────────────────────────
    redis_url: str = Field(default="redis://redis:6379", description="Redis DSN")
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: str = Field(default="", description="Redis password (optional, leave empty for no-auth)")

    # Redis Streams
    redis_stream_raw_events: str = "intelligence.events.raw"
    redis_stream_anomaly_events: str = "intelligence.events.anomaly"
    redis_stream_incidents: str = "intelligence.incidents"
    redis_consumer_group: str = "neuralops-consumers"

    # ── ChromaDB ─────────────────────────────────────────────────────────────
    chroma_host: str = "chromadb"
    chroma_port: int = 8000
    chromadb_host: str = "chromadb"
    chromadb_port: int = 8000
    chromadb_collection_incidents: str = "neuralops_incidents"
    chromadb_collection_runbooks: str = "neuralops_runbooks"

    # ── MongoDB ───────────────────────────────────────────────────────────────
    mongo_user: str = Field(default="neuralops", description="MongoDB username")
    mongo_password: str = Field(default="neuralops123", description="MongoDB password")
    mongodb_url: str = Field(
        default="mongodb://neuralops:neuralops123@mongodb:27017/neuralops?authSource=admin",
        description="MongoDB Motor async connection DSN"
    )
    mongodb_db_name: str = "neuralops"


    # ── LLM — OpenRouter (Primary) ───────────────────────────────────────────
    openrouter_api_key: str = Field(default="", description="OpenRouter API key — get free key at openrouter.ai")
    openrouter_model: str = "meta-llama/llama-3.1-8b-instruct:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # ── LLM — Ollama / Phi-3 ─────────────────────────────────────────────────
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "phi3:mini"
    ollama_request_timeout_seconds: int = 60
    ollama_max_retries: int = 2

    # Active primary LLM provider
    llm_primary_provider: Literal["openrouter", "phi3"] = "openrouter"

    # ── JWT ──────────────────────────────────────────────────────────────────
    jwt_secret_key: str = Field(
        default="neuralops-dev-secret-change-in-production-32chars",
        description="256-bit JWT signing secret"
    )
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 7

    # Fernet encryption key for integration credentials
    secret_key: str = Field(
        default="neuralops-secret-key-change-in-production-12345",
        description="Secret key used for Fernet encryption"
    )

    # ── API ──────────────────────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8888
    api_log_level: str = "info"
    cors_origins: list[str] = Field(default_factory=list)
    api_rate_limit_per_minute: int = 120


    # ── Environment ──────────────────────────────────────────────────────────
    default_environment: str = "production"

    # ── ML Engine ────────────────────────────────────────────────────────────
    anomaly_score_warn: float = 0.60
    anomaly_score_critical: float = 0.80
    isolation_forest_contamination: float = 0.05
    lstm_sequence_length: int = 60
    lstm_hidden_size: int = 64
    lstm_num_layers: int = 2
    lstm_dropout: float = 0.2
    auto_execution_confidence_threshold: float = 0.85
    connector_poll_interval_seconds: int = 60

    # ── Model Artifacts ──────────────────────────────────────────────────────
    models_dir: str = "./models"
    lstm_model_path: str = "./models/lstm_anomaly_v1.pt"
    isolation_forest_model_path: str = "./models/isolation_forest_v1.joblib"
    prophet_models_dir: str = "./models/prophet"

    # ── Retraining ───────────────────────────────────────────────────────────
    retraining_schedule_cron: str = "0 2 * * 0"
    retraining_min_f1_threshold: float = 0.80
    retraining_lookback_days: int = 7

    # ── Cloud Connectors ─────────────────────────────────────────────────────
    aws_enabled: bool = False
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_default_region: str = "us-east-1"
    aws_cloudwatch_log_group: str = "/neuralops/monitored-services"
    aws_cost_explorer_lookback_days: int = 7

    azure_enabled: bool = False
    azure_tenant_id: str = ""
    azure_client_id: str = ""
    azure_client_secret: str = ""
    azure_subscription_id: str = ""
    azure_resource_group: str = ""

    gcp_enabled: bool = False
    gcp_project_id: str = ""
    gcp_default_region: str = "us-central1"
    google_application_credentials: str = ""
    gcp_billing_account_id: str = ""

    # ── DevOps Integrations ──────────────────────────────────────────────────
    pagerduty_enabled: bool = False
    pagerduty_api_key: str = ""
    pagerduty_service_key: str = ""
    pagerduty_from_email: str = "alerts@company.com"

    slack_enabled: bool = False
    slack_bot_token: str = ""
    slack_signing_secret: str = ""
    slack_alerts_channel: str = "#neuralops-alerts"
    slack_chatbot_channel: str = "#neuralops-chatbot"

    jira_enabled: bool = False
    jira_base_url: str = ""
    jira_user_email: str = ""
    jira_api_token: str = ""
    jira_project_key: str = "OPS"
    jira_incident_issue_type: str = "Incident"

    github_enabled: bool = False
    github_token: str = ""
    github_org: str = ""
    github_monitored_repos_raw: str = Field(default="", alias="github_monitored_repos")

    @property
    def github_monitored_repos(self) -> list[str]:
        """Parse GITHUB_MONITORED_REPOS from CSV or JSON array format."""
        v = self.github_monitored_repos_raw.strip()
        if not v:
            return []
        if v.startswith("["):
            import json
            try:
                return [r.strip() for r in json.loads(v) if r.strip()]
            except Exception:
                pass
        return [r.strip() for r in v.split(",") if r.strip()]

    gitlab_enabled: bool = False
    gitlab_base_url: str = "https://gitlab.com"
    gitlab_token: str = ""
    gitlab_group_id: str = ""

    jenkins_enabled: bool = False
    jenkins_base_url: str = ""
    jenkins_user: str = ""
    jenkins_api_token: str = ""

    terraform_enabled: bool = False
    terraform_cloud_token: str = ""
    terraform_organization: str = ""
    terraform_state_backend_url: str = "https://app.terraform.io"

    kubectl_enabled: bool = False
    kubeconfig_path: str = "/root/.kube/config"
    kubectl_allowed_namespaces: list[str] = Field(default_factory=list)
    kubectl_action_allowlist: list[str] = Field(default_factory=list)

    @field_validator("kubectl_allowed_namespaces", "kubectl_action_allowlist", mode="before")
    @classmethod
    def parse_csv_list(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    ansible_enabled: bool = False
    ansible_playbooks_dir: str = "/app/ansible/playbooks"
    ansible_inventory_path: str = "/app/ansible/inventory/hosts.ini"
    ansible_vault_password_file: str = ""

    # ── Observability ────────────────────────────────────────────────────────
    log_level: str = "INFO"
    log_format: str = "json"
    sentry_dsn: str = ""
    enable_prometheus_metrics: bool = True


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached singleton Settings instance."""
    return Settings()
