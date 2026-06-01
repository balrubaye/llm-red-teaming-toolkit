"""Locate bundled assets (red-team corpus, default rubrics) on disk.

Works for both editable installs (``pip install -e .``) and wheel installs by
trying :mod:`importlib.resources` first and falling back to a path relative to
the source tree.
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path


def _from_resources() -> Path | None:
    try:
        files = importlib.resources.files("reagent") / "_bundled_corpus"
    except (ModuleNotFoundError, FileNotFoundError):
        return None
    try:
        p = Path(str(files))
    except (TypeError, ValueError):
        return None
    return p if p.is_dir() else None


def _from_source_tree() -> Path | None:
    # src/reagent/paths.py -> repo root is two levels up from `reagent/`.
    here = Path(__file__).resolve().parent
    candidate = here.parent.parent / "redteam_corpus"
    return candidate if candidate.is_dir() else None


def bundled_corpus_dir() -> Path:
    """Return the absolute path to the bundled red-team corpus directory."""
    for finder in (_from_resources, _from_source_tree):
        path = finder()
        if path is not None:
            return path
    raise FileNotFoundError(
        "could not locate the bundled red-team corpus. Set --corpus explicitly "
        "or reinstall reagent-eval."
    )


__all__ = ["bundled_corpus_dir"]
