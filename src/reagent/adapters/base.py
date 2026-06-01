"""Adapter protocol and shared errors."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from reagent.models import ChatRequest, ChatResponse


class AdapterError(Exception):
    """Base class for adapter errors."""


class TransientError(AdapterError):
    """Recoverable error — runner may retry."""


class RateLimitError(TransientError):
    """Provider returned 429 or equivalent. Runner should back off."""


@runtime_checkable
class Adapter(Protocol):
    """Provider adapter contract.

    Implementations MUST be safe to share across concurrent tasks; the runner
    creates one adapter per provider and reuses it. State that is not safe to
    share (e.g., a synchronous HTTP client) should be wrapped in a lock or
    re-created per call.
    """

    name: str  # e.g. "ollama"

    def supports(self, model_str: str) -> bool:
        """Return True if this adapter handles ``model_str``.

        Model strings are of the form ``"<provider>:<name>"``. Adapters typically
        compare the prefix before the first colon.
        """
        ...

    async def complete(self, request: ChatRequest) -> ChatResponse:
        """Execute a single completion. Must not retry internally."""
        ...

    def supports_seed(self) -> bool:
        """Whether the provider honors ``params.seed`` for reproducibility."""
        ...

    async def aclose(self) -> None:
        """Release any held resources (HTTP pools, etc.). Idempotent."""
        ...


def parse_model_string(model: str) -> tuple[str, str]:
    """Split a model string into ``(provider, remainder)``.

    Examples
    --------
    >>> parse_model_string("ollama:llama3.1:8b")
    ('ollama', 'llama3.1:8b')
    >>> parse_model_string("openai:gpt-4.1")
    ('openai', 'gpt-4.1')
    """
    if ":" not in model:
        raise ValueError(
            f"model string {model!r} must be of form 'provider:name'; "
            "e.g. 'ollama:llama3.1:8b'"
        )
    provider, _, name = model.partition(":")
    if not provider or not name:
        raise ValueError(f"model string {model!r} has empty provider or name")
    return provider, name


__all__ = [
    "Adapter",
    "AdapterError",
    "RateLimitError",
    "TransientError",
    "parse_model_string",
]
