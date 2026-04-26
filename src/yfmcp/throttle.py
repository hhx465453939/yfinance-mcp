"""Rate limiting and caching for yfinance HTTP requests.

Provides:
- asyncio-based request throttle (minimum interval between calls)
- shared CachedLimiterSession (requests-cache + requests-ratelimiter)
- convenience wrappers for common yfinance operations

Configurable via environment variables:
- YFMCP_MIN_INTERVAL: minimum seconds between requests (default: 1.5)
- YFMCP_CACHE_DIR: cache directory path (default: /tmp/yfmcp-cache)
- YFMCP_CACHE_EXPIRE: cache TTL in seconds (default: 300)
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from loguru import logger

# ---------------------------------------------------------------------------
# Asyncio throttle — always active, zero dependencies
# ---------------------------------------------------------------------------

_MIN_INTERVAL = float(os.environ.get("YFMCP_MIN_INTERVAL", "1.5"))
_lock = asyncio.Lock()
_last_request: float = 0.0


async def throttle() -> None:
    """Enforce minimum interval between consecutive yfinance requests."""
    global _last_request
    async with _lock:
        now = time.monotonic()
        wait = _MIN_INTERVAL - (now - _last_request)
        if wait > 0:
            logger.debug("yfmcp throttle: waiting {:.2f}s", wait)
            await asyncio.sleep(wait)
        _last_request = time.monotonic()


# ---------------------------------------------------------------------------
# Cached + rate-limited session (graceful degradation)
# ---------------------------------------------------------------------------

_session = None
_session_initialized: bool = False


def _init_session():
    global _session, _session_initialized
    if _session_initialized:
        return
    _session_initialized = True
    try:
        from requests import Session
        from requests_cache import CacheMixin, SQLiteCache
        from requests_ratelimiter import LimiterMixin, Rate, SingleBucketFactory, InMemoryBucket

        class CachedLimiterSession(CacheMixin, LimiterMixin, Session):
            pass

        cache_dir = Path(os.environ.get("YFMCP_CACHE_DIR", "/tmp/yfmcp-cache"))
        cache_dir.mkdir(parents=True, exist_ok=True)
        expire = int(os.environ.get("YFMCP_CACHE_EXPIRE", "300"))

        rates = [Rate(1, 3)]
        _session = CachedLimiterSession(
            rates=rates,
            bucket_factory=SingleBucketFactory(InMemoryBucket(rates)),
            backend=SQLiteCache(str(cache_dir / "requests"), expire_after=expire),
        )
        logger.info("yfmcp: session cache enabled at {}", cache_dir)
    except ImportError:
        logger.warning("yfmcp: requests-cache/requests-ratelimiter not installed, cache disabled")


def get_session():
    """Return the shared CachedLimiterSession, or None if unavailable."""
    _init_session()
    return _session


# ---------------------------------------------------------------------------
# Convenience wrappers
# ---------------------------------------------------------------------------


async def make_ticker(symbol: str):
    """Create a rate-limited yfinance Ticker with shared session."""
    import yfinance as yf

    await throttle()
    return await asyncio.to_thread(yf.Ticker, symbol, session=get_session())


async def throttled_download(**kwargs):
    """Rate-limited yf.download with shared session."""
    import yfinance as yf

    await throttle()
    s = get_session()
    if s:
        kwargs = {**kwargs, "session": s}
    return await asyncio.to_thread(yf.download, **kwargs)
