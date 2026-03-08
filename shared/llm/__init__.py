"""
shared/llm/__init__.py
───────────────────────
LLM entry point — exports the unified llm_service singleton.
OpenRouter is primary; Phi-3 via Ollama is automatic fallback.
"""
from __future__ import annotations

from shared.llm.gemini_provider import LLMService, llm_service

__all__ = ["LLMService", "llm_service"]


def get_llm_provider() -> LLMService:
    """Backward-compat shim. Returns the llm_service singleton."""
    return llm_service
