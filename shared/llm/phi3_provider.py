"""
shared/llm/phi3_provider.py
────────────────────────────
Phi-3 Mini via Ollama — LLMProvider implementation for local fast inference.
Used for quick log classification, alert triage, code error detection, and low-latency decisions.

Includes:
  - generate / generate_json / stream (standard LLMProvider interface)
  - analyze_file_for_errors(): full code review via Phi-3 with MongoDB RL weight filtering
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime
from typing import Any, AsyncIterator

import httpx
import structlog

from shared.interfaces import LLMProvider, LLMProviderError

logger = structlog.get_logger(__name__)

# Valid error types the model is constrained to use
VALID_ERROR_TYPES = {
    "syntax_error", "runtime_error", "null_reference", "missing_error_handling",
    "security_vulnerability", "performance_issue", "resource_leak", "hardcoded_secret",
    "missing_input_validation", "logic_error", "deprecated_api",
}


class Phi3Provider(LLMProvider):
    """
    Phi-3 Mini running locally via Ollama.
    Falls back from Gemini when the API is rate-limited.
    Also used directly for low-latency triage and code error detection.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model_name: str = "phi3:mini",
        timeout_seconds: int = 60,
        max_retries: int = 2,
    ) -> None:
        self._base_url = base_url
        self._model_name = model_name
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._available = True
        self._last_failure_at: float | None = None

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        for attempt in range(self._max_retries):
            try:
                async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
                    resp = await client.post(
                        "/api/chat",
                        json={
                            "model": self._model_name,
                            "messages": messages,
                            "stream": False,
                            "options": {"temperature": temperature, "num_predict": max_tokens},
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    self._available = True
                    return data["message"]["content"]
            except Exception as exc:
                logger.warning("phi3_generate_error", attempt=attempt + 1, error=str(exc))
                if attempt == self._max_retries - 1:
                    self._available = False
                    self._last_failure_at = time.monotonic()
                    raise LLMProviderError(self.provider_name, str(exc)) from exc
                await asyncio.sleep(2 ** attempt)
        raise LLMProviderError(self.provider_name, "Max retries exceeded")

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        json_system = (
            f"{system_prompt}\n\n"
            "IMPORTANT: Respond with valid JSON only. No markdown, no explanation."
        )
        raw = await self.generate(json_system, user_prompt, temperature, max_tokens)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise LLMProviderError(
                self.provider_name,
                f"Non-JSON output: {cleaned[:200]}",
            ) from exc

    async def stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
                async with client.stream(
                    "POST",
                    "/api/chat",
                    json={
                        "model": self._model_name,
                        "messages": messages,
                        "stream": True,
                        "options": {"temperature": temperature, "num_predict": max_tokens},
                    },
                ) as response:
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                            delta = chunk.get("message", {}).get("content", "")
                            if delta:
                                yield delta
                            if chunk.get("done", False):
                                break
                        except json.JSONDecodeError:
                            continue
        except Exception as exc:
            raise LLMProviderError(self.provider_name, str(exc)) from exc

    async def get_embedding(self, text: str) -> list[float]:
        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=30) as client:
                resp = await client.post(
                    "/api/embeddings",
                    json={"model": self._model_name, "prompt": text},
                )
                resp.raise_for_status()
                return resp.json()["embedding"]
        except Exception as exc:
            raise LLMProviderError(
                self.provider_name,
                f"Embedding failed: {exc}",
            ) from exc

    async def analyze_file_for_errors(
        self,
        file_path: str,
        file_content: str,
        language: str,
        mongo_db: Any | None = None,
    ) -> list[dict[str, Any]]:
        """
        Analyze a source file for real errors using Phi-3 Mini.

        The prompt instructs the model to:
        - Find ONLY genuine errors that actually exist in the code
        - Return [] if the code is clean
        - Use a strict JSON schema with confidence_score

        Errors are filtered by the RL weight threshold for each error_type
        (fetched from MongoDB, defaulting to 0.5 if no weight exists yet).
        All qualifying errors are returned for the caller to save to MongoDB.
        """
        if not file_content or len(file_content.strip()) < 30:
            return []

        # Cap content to avoid token limits — analyze the first 4000 chars
        content_snippet = file_content[:4000]

        prompt = (
            f"You are a strict senior code reviewer for {language} code.\n"
            f"File: {file_path}\n\n"
            "INSTRUCTIONS:\n"
            "1. Read the code below carefully.\n"
            "2. Identify ONLY genuine errors and bugs that ACTUALLY EXIST in this code.\n"
            "3. DO NOT invent problems. If the code is correct, return an empty JSON array: []\n"
            "4. For each real error, return a JSON object in the array below.\n\n"
            f"```{language}\n{content_snippet}\n```\n\n"
            "Return a JSON array (and NOTHING else). Each element must have these exact fields:\n"
            '{\n'
            '  "line_number": <integer>,\n'
            '  "error_type": <one of: syntax_error|runtime_error|null_reference|missing_error_handling|'
            'security_vulnerability|performance_issue|resource_leak|hardcoded_secret|'
            'missing_input_validation|logic_error|deprecated_api>,\n'
            '  "severity": <"P1" for critical bugs | "P2" for serious issues | "P3" for warnings | "P4" for suggestions>,\n'
            '  "title": <short specific description, max 80 chars>,\n'
            '  "description": <detailed explanation of why this is a problem in this specific code>,\n'
            '  "suggestion": <concrete fix recommendation>,\n'
            '  "code_before": <exact problematic code snippet from the file>,\n'
            '  "code_after": <corrected version of that same snippet>,\n'
            '  "confidence_score": <float 0.0 to 1.0 — how certain you are this is a real issue>\n'
            '}\n\n'
            'If NO issues exist, return: []\n'
            'Return ONLY the JSON array, no explanation, no markdown.'
        )

        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=90) as client:
                resp = await client.post(
                    "/api/generate",
                    json={
                        "model": self._model_name,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"temperature": 0.1, "top_p": 0.9, "num_predict": 2048},
                    },
                )
                resp.raise_for_status()
                text = resp.json().get("response", "[]")
        except Exception as exc:
            logger.warning("phi3_analyze_error", file=file_path, error=str(exc))
            return []

        # Parse the JSON array from the response — find first [ and last ]
        start = text.find("[")
        end = text.rfind("]") + 1
        if start < 0 or end <= start:
            return []

        try:
            raw_issues = json.loads(text[start:end])
        except json.JSONDecodeError as exc:
            logger.warning("phi3_json_parse_error", file=file_path, error=str(exc))
            return []

        if not isinstance(raw_issues, list):
            return []

        # Fetch RL weight thresholds from MongoDB (if available)
        rl_thresholds: dict[str, float] = {}
        if mongo_db is not None:
            try:
                async for doc in mongo_db["rl_weights"].find({}, {"error_type": 1, "confidence_threshold": 1}):
                    rl_thresholds[doc["error_type"]] = doc.get("confidence_threshold", 0.5)
            except Exception as exc:
                logger.warning("rl_weights_fetch_error", error=str(exc))

        # Filter and normalize issues
        qualified: list[dict[str, Any]] = []
        for item in raw_issues:
            if not isinstance(item, dict):
                continue

            error_type = item.get("error_type", "")
            if error_type not in VALID_ERROR_TYPES:
                continue  # reject hallucinated error types

            confidence = float(item.get("confidence_score", 0.0))
            threshold = rl_thresholds.get(error_type, 0.5)

            if confidence < threshold:
                continue  # below RL threshold for this error type

            severity = item.get("severity", "P3")
            if severity not in ("P1", "P2", "P3", "P4"):
                severity = "P3"

            qualified.append({
                "file_path": file_path,
                "line_number": int(item.get("line_number", 1)),
                "language": language,
                "error_type": error_type,
                "severity": severity,
                "title": str(item.get("title", ""))[:200],
                "description": str(item.get("description", "")),
                "suggestion": str(item.get("suggestion", "")),
                "code_before": str(item.get("code_before", ""))[:1000],
                "code_after": str(item.get("code_after", ""))[:1000],
                "confidence_score": round(confidence, 4),
                "source": "phi3",
                # Legacy fields for backward compat with old issues endpoint
                "file": file_path,
                "issue_type": error_type,
            })

        return qualified

    async def health_check(self) -> dict[str, Any]:
        """Test Phi-3/Ollama connectivity. Never raises."""
        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=5) as client:
                resp = await client.get("/api/tags")
                resp.raise_for_status()
                models = resp.json().get("models", [])
                phi3_model = next(
                    (m for m in models if m.get("name", "").startswith("phi3")), None
                )
                if phi3_model:
                    return {"ok": True, "model": phi3_model["name"]}
                return {"ok": False, "error": "phi3 not installed — run: ollama pull phi3:mini"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    @property
    def provider_name(self) -> str:
        return f"ollama/{self._model_name}"

    @property
    def is_available(self) -> bool:
        if not self._available and self._last_failure_at is not None:
            if time.monotonic() - self._last_failure_at > 30:
                self._available = True
        return self._available
