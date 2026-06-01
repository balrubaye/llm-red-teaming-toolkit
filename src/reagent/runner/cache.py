"""Content-addressable response cache.

Layout::

    <root>/
        <first-2-hex>/
            <full-hash>.json

The two-character shard prevents directories with tens of thousands of entries
on heavy users' machines. Cache hits set ``cached=True`` on the returned
:class:`ChatResponse` so the runner can count them separately.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from reagent.models import ChatRequest, ChatResponse

_log = logging.getLogger(__name__)

_DEFAULT_DIR = Path(os.environ.get("REAGENT_CACHE_DIR") or "~/.cache/reagent/responses")


class ResponseCache:
    def __init__(self, root: Path | str | None = None, *, enabled: bool = True) -> None:
        self._enabled = enabled
        self._root = Path(root or _DEFAULT_DIR).expanduser()
        if self._enabled:
            self._root.mkdir(parents=True, exist_ok=True)
        self.hits = 0
        self.misses = 0

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _path_for(self, key: str) -> Path:
        return self._root / key[:2] / f"{key}.json"

    def get(self, request: ChatRequest) -> ChatResponse | None:
        if not self._enabled:
            return None
        path = self._path_for(request.cache_key())
        if not path.is_file():
            self.misses += 1
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            resp = ChatResponse.model_validate(data)
        except Exception as exc:
            # A corrupt cache entry should never break a run.
            _log.warning("ignoring corrupt cache entry %s: %s", path, exc)
            self.misses += 1
            return None
        self.hits += 1
        return resp.model_copy(update={"cached": True})

    def put(self, request: ChatRequest, response: ChatResponse) -> None:
        if not self._enabled or response.cached:
            return
        path = self._path_for(request.cache_key())
        path.parent.mkdir(parents=True, exist_ok=True)
        # Avoid persisting the (possibly large) raw provider payload to keep
        # cache files small and forward-compatible.
        payload = response.model_dump(mode="json", exclude={"raw", "cached"})
        try:
            # Atomic write: tmp file + rename.
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload), encoding="utf-8")
            tmp.replace(path)
        except OSError as exc:  # disk full, perms, etc.
            _log.warning("failed to write cache entry %s: %s", path, exc)


__all__ = ["ResponseCache"]
