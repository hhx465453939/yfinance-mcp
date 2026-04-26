"""Application-level result cache for yfinance MCP tool responses.

Caches the final JSON/string output of each tool call, keyed by
tool name + parameters.  Does NOT touch the HTTP session layer,
so it is fully compatible with yfinance's internal curl_cffi usage.

Enable by setting YFMCP_RESULT_CACHE_DIR to a writable directory path.
When unset (default), caching is disabled.

Optional:
- YFMCP_RESULT_CACHE_TTL: cache TTL in seconds (default: 300)
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from loguru import logger


class ResultCache:
    def __init__(self):
        self._dir: Path | None = None
        self._enabled: bool | None = None
        self._ttl: int = int(os.environ.get("YFMCP_RESULT_CACHE_TTL", "300"))

    @property
    def enabled(self) -> bool:
        if self._enabled is None:
            path = os.environ.get("YFMCP_RESULT_CACHE_DIR", "")
            if path:
                self._dir = Path(path)
                self._dir.mkdir(parents=True, exist_ok=True)
                self._enabled = True
                logger.info("yfmcp: result cache at {} (ttl={}s)", self._dir, self._ttl)
            else:
                self._enabled = False
        return self._enabled

    @property
    def ttl(self) -> int:
        return self._ttl

    def _key(self, name: str, args: dict) -> str:
        raw = name + "|" + json.dumps(args, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def get(self, name: str, args: dict) -> str | None:
        """Return cached result string, or None on miss / expiry."""
        if not self.enabled:
            return None
        f = self._dir / (self._key(name, args) + ".json")
        if not f.exists():
            return None
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            if time.time() - d.get("ts", 0) > self._ttl:
                return None
            logger.debug("yfmcp: cache hit {}", name)
            return d["data"]
        except Exception:
            return None

    def put(self, name: str, args: dict, data: str) -> None:
        """Store result string in cache."""
        if not self.enabled or not data:
            return
        f = self._dir / (self._key(name, args) + ".json")
        try:
            f.write_text(
                json.dumps({"ts": time.time(), "name": name, "args": args, "data": data}, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.debug("yfmcp: cache write failed: {}", exc)


cache = ResultCache()
