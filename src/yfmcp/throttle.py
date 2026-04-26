"""Rate limiting for yfinance HTTP requests.

Provides:
- asyncio-based request throttle (minimum interval between calls)

yfinance >= 0.2.36 uses curl_cffi internally for Yahoo Finance anti-scraping.
requests-cache sessions are incompatible with curl_cffi, so we only use
asyncio-level throttling to avoid 429 rate limits.

Configurable via environment variables:
- YFMCP_MIN_INTERVAL: minimum seconds between requests (default: 1.5)
"""

from __future__ import annotations

import asyncio
import os
import time

from loguru import logger

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


async def make_ticker(symbol: str):
    """Create a rate-limited yfinance Ticker (no session override)."""
    import yfinance as yf

    await throttle()
    return await asyncio.to_thread(yf.Ticker, symbol)


async def throttled_download(**kwargs):
    """Rate-limited yf.download (no session override)."""
    import yfinance as yf

    await throttle()
    return await asyncio.to_thread(yf.download, **kwargs)
