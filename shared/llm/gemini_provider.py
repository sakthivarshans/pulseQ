"""
shared/llm/gemini_provider.py
──────────────────────────────
LLMService — OpenRouter as primary, Phi-3 via Ollama as fallback.
Uses pure httpx async HTTP calls. No SDK required.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from typing import AsyncGenerator

import httpx

from shared.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class LLMService:
    def __init__(self) -> None:
        self.openrouter_available = bool(settings.openrouter_api_key)
        self.openrouter_headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "HTTP-Referer": "https://neuralops.io",
            "X-Title": "NeuralOps AI DevOps Platform",
            "Content-Type": "application/json",
        }
        self.model = settings.openrouter_model
        self.base_url = settings.openrouter_base_url
        self.ollama_url = settings.ollama_base_url
        self.phi3_model = "phi3:mini"
        self._request_times: deque[float] = deque(maxlen=60)

        if self.openrouter_available:
            logger.info(f"LLMService initialized with OpenRouter model: {self.model}")
        else:
            logger.warning("OPENROUTER_API_KEY not set — will use Phi-3 fallback only")

    # ── Rate limiting ──────────────────────────────────────────────────────────
    def _rate_limit_check(self) -> None:
        now = time.time()
        recent = [t for t in self._request_times if now - t < 60]
        self._request_times = deque(recent, maxlen=60)
        if len(self._request_times) >= 18:
            oldest = self._request_times[0]
            wait = 60 - (now - oldest) + 1
            if wait > 0:
                time.sleep(wait)
        self._request_times.append(time.time())

    # ── Public API ─────────────────────────────────────────────────────────────
    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> str:
        if self.openrouter_available:
            try:
                return await self._openrouter_generate(
                    prompt, system_prompt, temperature, max_tokens
                )
            except Exception as e:
                logger.warning(f"OpenRouter failed: {e} — falling back to Phi-3")

        return await self._phi3_generate(prompt, system_prompt)

    async def stream(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        if self.openrouter_available:
            try:
                async for chunk in self._openrouter_stream(
                    prompt, system_prompt, temperature
                ):
                    yield chunk
                return
            except Exception as e:
                logger.warning(f"OpenRouter stream failed: {e} — falling back to Phi-3")
                yield "\n\n"

        response = await self._phi3_generate(prompt, system_prompt)
        yield response

    # ── OpenRouter implementation ──────────────────────────────────────────────
    async def _openrouter_generate(
        self,
        prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self.openrouter_headers,
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": False,
                },
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            if not content:
                raise ValueError("Empty response from OpenRouter")
            return content

    async def _openrouter_stream(
        self,
        prompt: str,
        system_prompt: str,
        temperature: float,
    ) -> AsyncGenerator[str, None]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self.openrouter_headers,
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": 1024,
                    "stream": True,
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        delta = data["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                            await asyncio.sleep(0)
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

    # ── Phi-3 via Ollama fallback ──────────────────────────────────────────────
    async def _phi3_generate(self, prompt: str, system_prompt: str = "") -> str:
        full = f"{system_prompt}\n\n{prompt}".strip() if system_prompt else prompt
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                response = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.phi3_model,
                        "prompt": full,
                        "stream": False,
                        "options": {"temperature": 0.7, "top_p": 0.9},
                    },
                )
                return response.json().get("response", "No response from Phi-3")
        except Exception as e:
            logger.error(f"Phi-3 generate error: {e}")
            return (
                f"Both OpenRouter and Phi-3 are currently unavailable. Error: {str(e)}"
            )

    # ── Health check ───────────────────────────────────────────────────────────
    async def health_check(self) -> dict:
        result: dict = {
            "openrouter": {"available": False, "model": self.model, "error": None},
            "phi3": {"available": False, "model": "phi3:mini", "error": None},
            "active_model": None,
        }

        if self.openrouter_available:
            try:
                response = await self._openrouter_generate(
                    "Reply with the single word: healthy", "", 0.1, 10
                )
                result["openrouter"]["available"] = True
                result["openrouter"]["test_response"] = response.strip()
                result["active_model"] = self.model
            except Exception as e:
                result["openrouter"]["error"] = str(e)
        else:
            result["openrouter"]["error"] = "API key not configured"

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self.ollama_url}/api/tags")
                models = r.json().get("models", [])
                phi3_found = any("phi3" in m.get("name", "") for m in models)
                result["phi3"]["available"] = phi3_found
                if not phi3_found:
                    result["phi3"]["error"] = "phi3:mini not installed"
                elif not result["active_model"]:
                    result["active_model"] = "phi3:mini"
        except Exception as e:
            result["phi3"]["error"] = str(e)

        if not result["active_model"]:
            result["active_model"] = "none — system degraded"

        return result

    # ── Backward-compat shim for code that calls provider-style methods ────────
    @property
    def provider_name(self) -> str:
        return f"openrouter/{self.model}" if self.openrouter_available else "phi3:mini"

    @property
    def is_available(self) -> bool:
        return self.openrouter_available


# Singleton exported for all consumers
llm_service = LLMService()
