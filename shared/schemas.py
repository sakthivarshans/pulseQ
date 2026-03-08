"""
shared/schemas.py
─────────────────
Central Pydantic v2 models shared across all NeuralOps modules.
These define the canonical data contracts for the entire platform.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Enumerations
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class EventType(StrEnum):
    METRIC = "metric"
    LOG = "log"
    TRACE = "trace"
    DEPLOYMENT = "deployment"
    ALERT = "alert"
    COST = "cost"
    INVENTORY = "inventory"


class CloudProvider(StrEnum):
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"
    GITHUB = "github"
    ON_PREMISE = "on_premise"
    UNKNOWN = "unknown"


class Severity(StrEnum):
    P1 = "P1"  # Critical — service down
    P2 = "P2"  # Major — severe degradation
    P3 = "P3"  # Minor — partial degradation
    P4 = "P4"  # Low — informational


class IncidentStatus(StrEnum):
    DETECTED = "detected"
    INVESTIGATING = "investigating"
    REMEDIATING = "remediating"
    RESOLVED = "resolved"
    POST_MORTEM = "post_mortem"
    FALSE_POSITIVE = "false_positive"


class AnomalyMetricType(StrEnum):
    CPU = "cpu"
    MEMORY = "memory"
    LATENCY = "latency"
    ERROR_RATE = "error_rate"
    THROUGHPUT = "throughput"
    SATURATION = "saturation"
    DISK_IO = "disk_io"
    NETWORK_IO = "network_io"
    NETWORK_IN = "network_in"
    NETWORK_OUT = "network_out"
    DB_CONNECTIONS = "db_connections"
    COST = "cost"
    # GitHub-specific
    CI_SUCCESS_RATE = "ci_success_rate"
    OPEN_PR_COUNT = "open_pr_count"
    COMMIT_FREQUENCY = "commit_frequency"


class ActionType(StrEnum):
    KUBECTL_ROLLOUT_RESTART = "kubectl_rollout_restart"
    KUBECTL_SCALE = "kubectl_scale"
    AWS_ASG_SCALE = "aws_asg_scale"
    AZURE_VMSS_SCALE = "azure_vmss_scale"
    GCP_MIG_SCALE = "gcp_mig_scale"
    CACHE_FLUSH = "cache_flush"
    PAGERDUTY_ALERT = "pagerduty_alert"
    SLACK_NOTIFICATION = "slack_notification"
    JIRA_TICKET = "jira_ticket"
    WEBHOOK = "webhook"
    ANSIBLE_PLAYBOOK = "ansible_playbook"


class ActionStatus(StrEnum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    SKIPPED = "skipped"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Core Ingestion Schema — IntelligenceEvent
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class ServiceTopology(BaseModel):
    """Service dependency metadata enriched during ingestion."""
    service_name: str
    namespace: str = "default"
    environment: str = "production"
    upstream_services: list[str] = Field(default_factory=list)
    downstream_services: list[str] = Field(default_factory=list)
    owner_team: str | None = None
    slo_target_availability: float | None = None  # e.g. 0.999
    slo_target_latency_p99_ms: float | None = None


class MetricPayload(BaseModel):
    """Metric data point within an IntelligenceEvent."""
    metric_name: str
    metric_type: AnomalyMetricType
    value: float
    unit: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    # Optional: historical window for the ML engine
    history_window: list[float] | None = None


class LogPayload(BaseModel):
    """Log entry within an IntelligenceEvent."""
    message: str
    level: str  # DEBUG, INFO, WARN, ERROR, FATAL
    logger: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class DeploymentPayload(BaseModel):
    """Deployment event data."""
    deploy_id: str
    service_name: str
    version: str
    previous_version: str | None = None
    deployed_by: str | None = None
    commit_sha: str | None = None
    commit_message: str | None = None
    repository_url: str | None = None
    pipeline_url: str | None = None
    environment: str = "production"
    status: str  # success | failed | rolling_back


class IntelligenceEvent(BaseModel):
    """
    Canonical event schema — the normalized data contract for the ingestion pipeline.
    All cloud connectors and OpenTelemetry data are normalized into this model
    before being published to the Redis Stream.
    """
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    source: str  # connector or integration name, e.g. "aws.cloudwatch"
    cloud_provider: CloudProvider = CloudProvider.UNKNOWN
    region: str | None = None
    account_id: str | None = None
    resource_id: str | None = None
    resource_type: str | None = None  # ec2, pod, rds, etc.
    service_name: str
    environment: str = "production"
    cluster_name: str | None = None

    # Typed payloads — exactly one should be populated based on event_type
    metric: MetricPayload | None = None
    log: LogPayload | None = None
    deployment: DeploymentPayload | None = None
    raw_payload: dict[str, Any] | None = None  # for types not yet typed

    # Enrichment fields added by ingestion pipeline
    topology: ServiceTopology | None = None
    ingested_at: datetime = Field(default_factory=datetime.utcnow)
    dedupe_key: str | None = None  # used for deduplication

    @field_validator("timestamp", "ingested_at", mode="before")
    @classmethod
    def parse_datetime(cls, v: Any) -> datetime:
        if isinstance(v, str):
            return datetime.fromisoformat(v)
        return v


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ML Engine Output — AnomalyEvent
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class ForecastPoint(BaseModel):
    timestamp: datetime
    predicted_value: float
    lower_bound: float
    upper_bound: float


class AnomalyEvent(BaseModel):
    """
    Output of the ML Anomaly Detection Engine.
    Published to Redis Stream: intelligence.events.anomaly
    """
    anomaly_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_event_id: str
    service_name: str
    environment: str = "production"
    detected_at: datetime = Field(default_factory=datetime.utcnow)

    affected_metrics: list[AnomalyMetricType]
    metric_values: dict[str, float]  # metric_name → current value
    baseline_values: dict[str, float]  # metric_name → expected baseline

    anomaly_score: float = Field(ge=0.0, le=1.0)  # 0=normal, 1=highly anomalous
    confidence_score: float = Field(ge=0.0, le=1.0)
    isolation_forest_score: float  # raw IF anomaly score
    lstm_reconstruction_error: float | None = None

    severity: Severity
    is_forecast: bool = False  # True if this is a predicted future anomaly
    forecast_horizon_minutes: int | None = None

    # Forecasted values for next 30 minutes
    forecast: list[ForecastPoint] = Field(default_factory=list)

    # Context
    contributing_factors: list[str] = Field(default_factory=list)
    cluster_name: str | None = None
    resource_id: str | None = None
    cloud_provider: CloudProvider = CloudProvider.UNKNOWN
    region: str | None = None

    # Traceability
    model_version: str | None = None
    detection_method: str = "hybrid"  # "lstm" | "isolation_forest" | "hybrid"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Orchestrator — Incident
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class BlastRadius(BaseModel):
    directly_affected_services: list[str]
    at_risk_services: list[str]  # downstream dependencies
    total_services_impacted: int
    estimated_user_impact_percentage: float | None = None
    slo_breached: bool = False
    slo_names_breached: list[str] = Field(default_factory=list)


class Incident(BaseModel):
    """
    Represents a grouped, correlated incident derived from one or more AnomalyEvents.
    Stored in PostgreSQL and published to Redis Stream: intelligence.incidents
    """
    incident_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str | None = None
    severity: Severity
    status: IncidentStatus = IncidentStatus.DETECTED

    # Timing
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    investigating_at: datetime | None = None
    remediating_at: datetime | None = None
    resolved_at: datetime | None = None
    post_mortem_at: datetime | None = None

    # Scope
    primary_service: str
    affected_services: list[str] = Field(default_factory=list)
    blast_radius: BlastRadius | None = None
    environment: str = "production"
    cloud_provider: CloudProvider = CloudProvider.UNKNOWN
    region: str | None = None

    # ML inputs
    correlated_anomaly_ids: list[str] = Field(default_factory=list)
    peak_anomaly_score: float = Field(ge=0.0, le=1.0)
    ml_confidence: float = Field(ge=0.0, le=1.0)

    # RCA & actions
    rca_id: str | None = None
    action_ids: list[str] = Field(default_factory=list)

    # Notification tracking
    pagerduty_incident_id: str | None = None
    slack_thread_ts: str | None = None
    jira_ticket_key: str | None = None

    # Metrics
    mttr_minutes: float | None = None  # set on resolution
    is_false_positive: bool = False

    # Metadata
    runbook_id: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    acknowledged_by: str | None = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RCA Engine — RCAResult
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class RemediationStep(BaseModel):
    step_number: int
    action: str
    rationale: str
    estimated_duration_minutes: int | None = None
    risk_level: str = "low"  # low | medium | high
    automation_eligible: bool = False
    action_type: ActionType | None = None
    action_parameters: dict[str, Any] = Field(default_factory=dict)


class SimilarIncident(BaseModel):
    incident_id: str
    title: str
    detected_at: datetime
    resolved_at: datetime | None
    similarity_score: float
    root_cause_summary: str | None
    resolution_summary: str | None
    mttr_minutes: float | None


class RCAResult(BaseModel):
    """
    Structured root cause analysis result produced by the RCA Engine.
    Stored in PostgreSQL linked to the incident.
    """
    rca_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    incident_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    llm_provider_used: str  # "gemini" | "phi3"

    # Core analysis
    root_cause_summary: str
    root_cause_confidence: float = Field(ge=0.0, le=1.0)
    primary_contributing_factor: str
    secondary_contributing_factors: list[str] = Field(default_factory=list)
    affected_components: list[str] = Field(default_factory=list)

    # Remediation plan
    remediation_steps: list[RemediationStep] = Field(default_factory=list)
    estimated_resolution_minutes: int | None = None
    recurrence_risk: str  # "low" | "medium" | "high"
    recurrence_reasoning: str | None = None

    # Context used
    similar_incidents: list[SimilarIncident] = Field(default_factory=list)
    logs_analyzed_count: int = 0
    deployments_checked_count: int = 0

    # Generated runbook
    runbook_markdown: str | None = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Action Executor — Action & Audit
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class ActionRequest(BaseModel):
    """A request to execute a remediation action."""
    action_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    incident_id: str
    rca_id: str | None = None
    action_type: ActionType
    parameters: dict[str, Any] = Field(default_factory=dict)
    requested_by: str = "system"  # "system" | user email
    confidence: float = Field(ge=0.0, le=1.0)
    requires_approval: bool = True


class ActionAuditRecord(BaseModel):
    """Full audit trail for an executed action."""
    audit_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    action_id: str
    incident_id: str
    action_type: ActionType
    status: ActionStatus
    parameters: dict[str, Any]

    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None

    state_before: dict[str, Any] = Field(default_factory=dict)
    state_after: dict[str, Any] = Field(default_factory=dict)
    diff_summary: str | None = None

    executed_by: str = "system"
    approved_by: str | None = None
    output: str | None = None
    error: str | None = None
    rolled_back: bool = False
    rollback_audit_id: str | None = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Chatbot — Message models
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatMessage(BaseModel):
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    role: ChatRole
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatContext(BaseModel):
    """Context object assembled before each LLM call in the chatbot."""
    session_id: str
    query: str
    active_incidents: list[Incident] = Field(default_factory=list)
    metric_summaries: dict[str, dict[str, float]] = Field(default_factory=dict)
    recent_logs: list[str] = Field(default_factory=list)
    recent_deployments: list[DeploymentPayload] = Field(default_factory=list)
    similar_past_incidents: list[SimilarIncident] = Field(default_factory=list)
    infrastructure_summary: str | None = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SLO Models
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class SLODefinition(BaseModel):
    slo_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    service_name: str
    slo_type: str  # "availability" | "latency" | "error_rate" | "throughput"
    target_percentage: float  # e.g. 99.9
    window_days: int = 30
    metric_query: str  # Prometheus-style metric selector


class SLOBurnRate(BaseModel):
    slo_id: str
    slo_name: str
    service_name: str
    current_burn_rate: float  # 1.0 = burning exactly at budget rate
    error_budget_remaining_percentage: float
    projected_exhaustion_hours: float | None = None  # None if budget is safe
    breach_alert_active: bool = False
    calculated_at: datetime = Field(default_factory=datetime.utcnow)
