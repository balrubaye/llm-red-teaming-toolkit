"""Provider adapters for Reagent.

Adapters register via the `reagent.adapters` entry-point group. Resolve a model
string like ``"ollama:llama3.1:8b"`` to an adapter with
:func:`registry.resolve_adapter`.
"""

from reagent.adapters.base import Adapter, AdapterError, RateLimitError, TransientError
from reagent.adapters.registry import (
    available_adapters,
    register_adapter,
    resolve_adapter,
)

__all__ = [
    "Adapter",
    "AdapterError",
    "RateLimitError",
    "TransientError",
    "available_adapters",
    "register_adapter",
    "resolve_adapter",
]
