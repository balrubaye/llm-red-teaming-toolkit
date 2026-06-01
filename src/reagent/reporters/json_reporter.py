"""Read and write canonical scorecard JSON."""

from __future__ import annotations

import json
from pathlib import Path

from reagent.models import Scorecard


def dump_json(scorecard: Scorecard, path: str | Path | None = None, *, indent: int = 2) -> str:
    """Serialize a scorecard. If ``path`` is given, also write the file."""
    payload = scorecard.model_dump(mode="json", exclude_none=False)
    text = json.dumps(payload, indent=indent, sort_keys=False)
    if path is not None:
        p = Path(path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return text


def load_json(path: str | Path) -> Scorecard:
    """Load a scorecard from JSON on disk."""
    p = Path(path).expanduser()
    data = json.loads(p.read_text(encoding="utf-8"))
    return Scorecard.model_validate(data)


__all__ = ["dump_json", "load_json"]
