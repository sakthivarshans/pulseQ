"""
shared/interfaces.py
────────────────────
Abstract base classes defining all platform integration contracts.
All modules and connectors implement these interfaces — never the concrete classes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

from shared.schemas import (
    ActionAuditRecord,
    ActionRequest,
    AnomalyEvent,
    DeploymentPayload,
    Incident,
    IntelligenceEvent,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LLM Abstraction Layer
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class LLMProvider(ABC):
    """
    Abstract LLM provider — all platform code calls ONLY this interface.
    Swap underlying implementations (Gemini, Phi-3, etc.) via configuration alone.
    """

    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> str:
        """
        Generate a text completion.
        Returns the raw model output string.
        Raises LLMProviderError on failure.
        """

    @abstractmethod
    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """
        Generate a JSON response.
        Must parse and return a Python dict.
        Raises LLMProviderError if output is not valid JSON.
        """

    @abstractmethod
    async def stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """
        Stream text tokens as they are generated.
        Each yielded value is a delta chunk (not accumulated).
        """

    @abstractmethod
    async def get_embedding(self, text: str) -> list[float]:
        """
        Generate a dense embedding vector for the given text.
        Used for semantic search in ChromaDB.
        """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider name, e.g. 'gemini-1.5-flash'."""

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """
        Quick health check — returns False if the provider is rate-limited
        or unreachable, triggering fallback to the next provider.
        """


class LLMProviderError(Exception):
    """Raised when an LLM provider call fails."""

    def __init__(self, provider: str, message: str, is_rate_limited: bool = False) -> None:
        self.provider = provider
        self.is_rate_limited = is_rate_limited
        super().__init__(f"[{provider}] {message}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Cloud Collector Interface
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class ResourceInventoryItem(ABC):
    """Provider-agnostic resource description."""
    resource_id: str
    resource_type: str
    name: str
    region: str
    tags: dict[str, str]
    status: str
    raw: dict[str, Any]


class CostDataPoint(ABC):
    """Cost data point for a single resource or service."""
    service_name: str
    resource_id: str | None
    amount_usd: float
    currency: str
    period_start: str
    period_end: str


class CollectorInterface(ABC):
    """
    Abstract base for all cloud connector implementations.
    Each cloud provider (AWS, Azure, GCP) implements this interface independently.
    New providers are added by implementing this interface — no other code changes required.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """E.g. 'aws', 'azure', 'gcp'."""

    @abstractmethod
    async def collect_metrics(
        self,
        service_names: list[str],
        start_time: str,
        end_time: str,
        metric_types: list[str] | None = None,
    ) -> list[IntelligenceEvent]:
        """
        Fetch metric data for the specified services over the given time range.
        Returns a list of normalized IntelligenceEvent objects (event_type=METRIC).
        """

    @abstractmethod
    async def collect_logs(
        self,
        service_names: list[str],
        start_time: str,
        end_time: str,
        filter_pattern: str | None = None,
        max_events: int = 1000,
    ) -> list[IntelligenceEvent]:
        """
        Fetch log entries for the specified services.
        Returns a list of normalized IntelligenceEvent objects (event_type=LOG).
        """

    @abstractmethod
    async def collect_traces(
        self,
        service_names: list[str],
        start_time: str,
        end_time: str,
    ) -> list[IntelligenceEvent]:
        """
        Fetch distributed traces.
        Returns normalized IntelligenceEvent objects (event_type=TRACE).
        """

    @abstractmethod
    async def get_resource_inventory(self) -> list[dict[str, Any]]:
        """
        Enumerate all monitored resources (instances, pods, databases, etc.).
        Returns a list of provider-agnostic resource dicts.
        """

    @abstractmethod
    async def get_cost_data(self, lookback_days: int = 7) -> list[dict[str, Any]]:
        """
        Retrieve cost breakdown data from the cloud billing API.
        Returns a list of cost data points normalized to USD.
        """

    @abstractmethod
    async def health_check(self) -> dict[str, Any]:
        """
        Verify connectivity to the cloud provider APIs.
        Returns {'status': 'ok'|'error', 'latency_ms': float, 'error': str|None}
        """


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DevOps Tool Integration Interface
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class ToolIntegrationInterface(ABC):
    """
    Abstract base for all DevOps tool integrations.
    Each tool (PagerDuty, Slack, Jira, etc.) implements this interface.
    New tools are added by implementing this interface — no other code changes.
    """

    @property
    @abstractmethod
    def tool_name(self) -> str:
        """E.g. 'pagerduty', 'slack', 'jira'."""

    @property
    @abstractmethod
    def is_enabled(self) -> bool:
        """Whether this integration is configured and enabled via .env."""

    @abstractmethod
    async def send_alert(self, incident: Incident, rca_summary: str | None = None) -> str | None:
        """
        Send an alert notification for the given incident.
        Returns an external alert ID or thread ID if applicable.
        """

    @abstractmethod
    async def create_ticket(
        self,
        incident: Incident,
        description: str,
        assignee: str | None = None,
    ) -> str | None:
        """
        Create a ticket in the target system (Jira, GitHub Issues, etc.).
        Returns the ticket ID or URL.
        """

    @abstractmethod
    async def get_recent_deployments(
        self,
        service_names: list[str] | None = None,
        lookback_hours: int = 24,
    ) -> list[DeploymentPayload]:
        """
        Retrieve recent deployment events from the DevOps tool.
        Returns a list of DeploymentPayload objects.
        """

    @abstractmethod
    async def execute_action(
        self,
        action_request: ActionRequest,
    ) -> ActionAuditRecord:
        """
        Execute a remediation action through this integration.
        Returns a completed ActionAuditRecord with full before/after state.
        """

    @abstractmethod
    async def health_check(self) -> dict[str, Any]:
        """
        Verify connectivity to the tool's API.
        Returns {'status': 'ok'|'error', 'latency_ms': float, 'error': str|None}
        """


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Memory Store Interface
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class MemoryStoreInterface(ABC):
    """
    Abstract interface for the self-learning memory system.
    Backed by ChromaDB with PostgreSQL for structured metadata.
    """

    @abstractmethod
    async def store_incident(
        self,
        incident: Incident,
        rca_summary: str | None = None,
        resolution_summary: str | None = None,
    ) -> str:
        """
        Store a resolved incident in vector memory.
        Returns the ChromaDB document ID for the stored embedding.
        """

    @abstractmethod
    async def find_similar_incidents(
        self,
        query_text: str,
        n_results: int = 5,
        min_similarity: float = 0.6,
    ) -> list[dict[str, Any]]:
        """
        Find the most semantically similar past incidents.
        Embeds query_text, queries ChromaDB, and returns ranked results.
        """

    @abstractmethod
    async def update_outcome(
        self,
        incident_id: str,
        outcome: str,  # "resolved" | "escalated" | "false_positive"
        resolution_summary: str | None = None,
        mttr_minutes: float | None = None,
    ) -> None:
        """Update the stored outcome for a previously indexed incident."""

    @abstractmethod
    async def get_training_data(
        self,
        lookback_days: int = 7,
    ) -> list[dict[str, Any]]:
        """Retrieve recent resolved incidents as training feature vectors."""
