"""Adapter discovery via entry points + manual registration."""

from __future__ import annotations

import logging
from importlib import metadata
from typing import TYPE_CHECKING

from reagent.adapters.base import Adapter, parse_model_string

if TYPE_CHECKING:
    from collections.abc import Iterable

_log = logging.getLogger(__name__)

_ENTRY_POINT_GROUP = "reagent.adapters"

# Process-wide registry. Adapters are stateless wrt registration so this is safe.
_registry: dict[str, type[Adapter]] = {}
_loaded_from_entry_points = False


def register_adapter(name: str, adapter_cls: type[Adapter]) -> None:
    """Register an adapter class by provider name. Overrides any prior entry."""
    _registry[name] = adapter_cls


# Built-in adapters that don't need entry-points (or can be overridden)
from reagent.adapters.exec import ScriptAdapter
register_adapter("exec", ScriptAdapter)


def _load_entry_points() -> None:
    global _loaded_from_entry_points
    if _loaded_from_entry_points:
        return
    try:
        eps: Iterable[metadata.EntryPoint] = metadata.entry_points(group=_ENTRY_POINT_GROUP)
    except Exception as exc:  # pragma: no cover — defensive
        _log.warning("failed to enumerate adapter entry points: %s", exc)
        _loaded_from_entry_points = True
        return
    for ep in eps:
        if ep.name in _registry:
            continue
        try:
            cls = ep.load()
        except Exception as exc:
            _log.warning("failed to load adapter entry point %r: %s", ep.name, exc)
            continue
        _registry[ep.name] = cls
    _loaded_from_entry_points = True


def available_adapters() -> list[str]:
    """List registered adapter names. Triggers entry-point discovery."""
    _load_entry_points()
    return sorted(_registry)


def resolve_adapter(model_str: str) -> Adapter:
    """Construct an adapter instance for the given model string.

    Raises
    ------
    ValueError
        If no adapter is registered for the provider prefix.
    """
    _load_entry_points()
    provider, _ = parse_model_string(model_str)
    cls = _registry.get(provider)
    if cls is None:
        raise ValueError(
            f"no adapter registered for provider {provider!r}; "
            f"available: {', '.join(available_adapters()) or '(none)'}"
        )
    return cls()


__all__ = ["available_adapters", "register_adapter", "resolve_adapter"]
