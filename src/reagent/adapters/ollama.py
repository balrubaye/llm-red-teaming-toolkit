"""Ollama adapter — talks to a local Ollama server over HTTP.

Ollama defaults to http://localhost:11434. Override with ``OLLAMA_HOST``.
Model strings have the form ``"ollama:<model>"`` where ``<model>`` is anything
Ollama recognizes, including names with colons (``llama3.1:8b``).
"""

from __future__ import annotations

import os
import time
from decimal import Decimal
from typing import Any

import httpx

from reagent.adapters.base import (
    AdapterError,
    RateLimitError,
    TransientError,
    parse_model_string,
)
from reagent.models import ChatRequest, ChatResponse, ChatUsage

_DEFAULT_HOST = "http://localhost:11434"
_TIMEOUT_S = 120.0


class OllamaAdapter:
    """Adapter for the local Ollama server."""

    name = "ollama"

    def __init__(self, host: str | None = None, timeout_s: float | None = None) -> None:
        self._host = (host or os.environ.get("OLLAMA_HOST") or _DEFAULT_HOST).rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._host,
            timeout=httpx.Timeout(timeout_s or _TIMEOUT_S),
        )

    def supports(self, model_str: str) -> bool:
        provider, _ = parse_model_string(model_str)
        return provider == self.name

    def supports_seed(self) -> bool:
        return True

    async def complete(self, request: ChatRequest) -> ChatResponse:
        _, model_name = parse_model_string(request.model)

        options: dict[str, Any] = {
            "temperature": request.params.temperature,
            "num_predict": request.params.max_tokens,
        }
        if request.params.top_p is not None:
            options["top_p"] = request.params.top_p
        if request.params.seed is not None:
            options["seed"] = request.params.seed
        if request.params.stop:
            options["stop"] = list(request.params.stop)

        payload = {
            "model": model_name,
            "messages": [{"role": m.role.value, "content": m.content} for m in request.messages],
            "options": options,
            "stream": False,
        }

        start = time.perf_counter()
        try:
            resp = await self._client.post("/api/chat", json=payload)
        except httpx.TimeoutException as exc:
            raise TransientError(f"ollama request timed out: {exc}") from exc
        except httpx.HTTPError as exc:
            raise TransientError(f"ollama network error: {exc}") from exc
        latency_ms = int((time.perf_counter() - start) * 1000)

        if resp.status_code == 429:
            raise RateLimitError("ollama returned 429")
        if resp.status_code >= 500:
            raise TransientError(f"ollama 5xx: {resp.status_code} {resp.text[:200]}")
        if resp.status_code >= 400:
            # 404 often means the model isn't pulled locally — give a clear hint.
            hint = ""
            if resp.status_code == 404:
                hint = f" — try `ollama pull {model_name}`"
            raise AdapterError(f"ollama error {resp.status_code}: {resp.text[:200]}{hint}")

        try:
            body = resp.json()
        except ValueError as exc:
            raise AdapterError(f"ollama returned non-JSON: {exc}") from exc

        message = body.get("message") or {}
        text = message.get("content") or ""

        usage = ChatUsage(
            prompt_tokens=int(body.get("prompt_eval_count") or 0),
            completion_tokens=int(body.get("eval_count") or 0),
        )

        return ChatResponse(
            text=text,
            model=request.model,
            usage=usage,
            latency_ms=latency_ms,
            cost_usd=Decimal("0"),  # local inference
            finish_reason="stop" if body.get("done") else None,
            cached=False,
            raw=body,
        )

    async def aclose(self) -> None:
        await self._client.aclose()


__all__ = ["OllamaAdapter"]
