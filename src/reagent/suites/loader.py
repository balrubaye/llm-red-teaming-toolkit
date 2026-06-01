"""YAML suite loader.

Three input shapes are accepted, in priority order:

1. **Suite file** — a YAML document with top-level ``name`` and ``cases`` keys.
2. **Case file** — a YAML document with a top-level ``id`` key. Wrapped in a
   synthetic single-case suite named after the file stem.
3. **Directory** — every ``*.yaml`` / ``*.yml`` file directly inside is loaded
   as a case file, and all cases are grouped into one synthetic suite named
   after the directory.

The loader records the original ``source_path`` and a sha256 of the bytes that
produced the in-memory suite, so the runner can persist the hash for
reproducibility.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from reagent.models import Case, Suite, SuiteDefaults


class SuiteLoadError(Exception):
    """Raised when a suite cannot be parsed or validated."""


def _normalize_assertion(item: Any) -> Any:
    """Accept the friendly YAML shorthand ``{<kind>: {...inner...}}`` and turn it
    into the canonical ``{"kind": "<kind>", **inner}`` shape Pydantic expects.

    Pass anything else through unchanged so Pydantic surfaces a clear error.
    """
    if not isinstance(item, dict):
        return item
    if "kind" in item:
        return item
    if len(item) == 1:
        kind, inner = next(iter(item.items()))
        if isinstance(inner, dict) and isinstance(kind, str):
            # `assert` items in YAML never collide with field names because
            # each kind's fields are namespaced under the kind key.
            return {"kind": kind, **inner}
    return item


def _normalize_case(case: Any) -> Any:
    if not isinstance(case, dict):
        return case
    raw = case.get("assert")
    if isinstance(raw, list):
        case = {**case, "assert": [_normalize_assertion(a) for a in raw]}
    return case


def _normalize_top(data: dict[str, Any]) -> dict[str, Any]:
    """Apply assertion normalization to either a suite or a single case dict."""
    if "cases" in data and isinstance(data["cases"], list):
        return {**data, "cases": [_normalize_case(c) for c in data["cases"]]}
    return _normalize_case(data)


def _read_yaml(path: Path) -> tuple[dict[str, Any], str]:
    """Read and parse YAML; return (normalized_data, sha256_of_raw_bytes).

    The sha256 is computed over the original bytes (not the normalized dict)
    so two suites that differ only in cosmetic whitespace produce different
    hashes — appropriate for reproducibility tracking.
    """
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise SuiteLoadError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise SuiteLoadError(f"{path}: expected a YAML mapping at the top level")
    return _normalize_top(data), sha


def _looks_like_suite(data: dict[str, Any]) -> bool:
    return "cases" in data and "name" in data


def _looks_like_case(data: dict[str, Any]) -> bool:
    return "id" in data


def _load_suite_file(path: Path) -> Suite:
    data, sha = _read_yaml(path)
    try:
        suite = Suite.model_validate(data)
    except ValidationError as exc:
        raise SuiteLoadError(f"{path}: invalid suite:\n{exc}") from exc
    suite.source_path = str(path)
    suite.content_sha256 = sha
    return suite


def _load_case_file(path: Path) -> tuple[Case, str]:
    data, sha = _read_yaml(path)
    try:
        case = Case.model_validate(data)
    except ValidationError as exc:
        raise SuiteLoadError(f"{path}: invalid case:\n{exc}") from exc
    return case, sha


def _wrap_cases_in_suite(
    name: str,
    description: str | None,
    cases_with_sha: list[tuple[Case, str]],
    source_path: Path,
) -> Suite:
    # Combine per-file hashes deterministically into one suite hash.
    h = hashlib.sha256()
    for _, sha in sorted(cases_with_sha, key=lambda x: x[0].id):
        h.update(sha.encode("ascii"))
    cases = [c for c, _ in cases_with_sha]
    suite = Suite(
        name=name,
        description=description,
        defaults=SuiteDefaults(),
        cases=cases,
    )
    suite.source_path = str(source_path)
    suite.content_sha256 = h.hexdigest()
    return suite


def _load_directory(path: Path) -> Suite:
    files = sorted(
        p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in {".yaml", ".yml"}
    )
    if not files:
        raise SuiteLoadError(f"{path}: no YAML files found")

    cases_with_sha: list[tuple[Case, str]] = []
    for f in files:
        data, sha = _read_yaml(f)
        if _looks_like_suite(data):
            raise SuiteLoadError(
                f"{f}: directory loads expect case files (with top-level 'id'); "
                "found a suite file. Load the suite file directly instead."
            )
        if not _looks_like_case(data):
            raise SuiteLoadError(f"{f}: not a recognizable case file (missing 'id')")
        try:
            case = Case.model_validate(data)
        except ValidationError as exc:
            raise SuiteLoadError(f"{f}: invalid case:\n{exc}") from exc
        cases_with_sha.append((case, sha))

    return _wrap_cases_in_suite(
        name=path.name,
        description=f"Cases loaded from directory {path}",
        cases_with_sha=cases_with_sha,
        source_path=path,
    )


def load_suite(path: str | Path) -> Suite:
    """Load a suite from a file or directory. Raises :class:`SuiteLoadError`."""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise SuiteLoadError(f"path does not exist: {p}")

    if p.is_dir():
        return _load_directory(p)

    data, sha = _read_yaml(p)
    if _looks_like_suite(data):
        return _load_suite_file(p)
    if _looks_like_case(data):
        case, _ = _load_case_file(p)
        return _wrap_cases_in_suite(
            name=p.stem,
            description=f"Single case loaded from {p}",
            cases_with_sha=[(case, sha)],
            source_path=p,
        )
    raise SuiteLoadError(
        f"{p}: unrecognized YAML shape — expected either a suite (with 'name' and "
        "'cases') or a case (with 'id')"
    )


__all__ = ["SuiteLoadError", "load_suite"]
