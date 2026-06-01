"""Shared pytest fixtures and the in-process fake adapter."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from decimal import Decimal

import pytest

from reagent.adapters import register_adapter
from reagent.adapters.base import parse_model_string
from reagent.models import ChatRequest, ChatResponse, ChatUsage

# Callable signature used by FakeAdapter.responder
ResponderFn = Callable[[ChatRequest], Awaitable[str] | str]


class FakeAdapter:
    """Test-only adapter. Provider scheme is ``fake:``.

    The behavior is controlled by a class-level responder set per test through
    :func:`set_fake_responder`. Defaults to echoing the last user message.
    """

    name = "fake"
    _responder: ResponderFn = staticmethod(lambda r: r.messages[-1].content)

    def supports(self, model_str: str) -> bool:
        provider, _ = parse_model_string(model_str)
        return provider == self.name

    def supports_seed(self) -> bool:
        return True

    async def complete(self, request: ChatRequest) -> ChatResponse:
        start = time.perf_counter()
        result = FakeAdapter._responder(request)
        if hasattr(result, "__await__"):
            text = await result  # type: ignore[misc]
        else:
            text = result  # type: ignore[assignment]
        latency_ms = int((time.perf_counter() - start) * 1000)
        return ChatResponse(
            text=str(text),
            model=request.model,
            usage=ChatUsage(prompt_tokens=10, completion_tokens=20),
            latency_ms=latency_ms,
            cost_usd=Decimal("0"),
            finish_reason="stop",
        )

    async def aclose(self) -> None:
        return None


def set_fake_responder(fn: ResponderFn) -> None:
    FakeAdapter._responder = staticmethod(fn)


@pytest.fixture(autouse=True)
def _register_fake_adapter():
    """Make the fake adapter available to every test, and reset its responder."""
    register_adapter("fake", FakeAdapter)
    yield
    # Reset to a benign default so tests don't bleed state.
    set_fake_responder(lambda r: r.messages[-1].content)


@pytest.fixture
def tmp_cache_dir(tmp_path):
    return tmp_path / "cache"
