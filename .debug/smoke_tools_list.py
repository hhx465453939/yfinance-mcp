r"""Deployment smoke check: start `yfmcp` via stdio and assert tools/list has 14 tools.

Run:
    .\.venv\Scripts\Activate.ps1
    python .debug\smoke_tools_list.py
"""

import asyncio
import sys

from mcp import ClientSession
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client

EXPECTED = {
    # Original (PRD §3)
    "yfinance_get_ticker_info",
    "yfinance_get_ticker_news",
    "yfinance_search",
    "yfinance_get_top",
    "yfinance_get_price_history",
    # Extended (PRD §5)
    "yfinance_download",
    "yfinance_get_history_advanced",
    "yfinance_get_financials",
    "yfinance_get_options",
    "yfinance_get_recommendations",
    "yfinance_get_calendar",
    "yfinance_get_holders",
    "yfinance_get_insider_transactions",
    "yfinance_get_fast_info",
}


async def main() -> int:
    params = StdioServerParameters(command="yfmcp")
    async with (
        stdio_client(params) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        result = await session.list_tools()
        names = {t.name for t in result.tools}

    print(f"Tools advertised: {len(names)}")
    for name in sorted(names):
        marker = "OK " if name in EXPECTED else "?? "
        print(f"  {marker}{name}")

    missing = EXPECTED - names
    extra = names - EXPECTED
    if missing:
        print(f"MISSING: {sorted(missing)}", file=sys.stderr)
    if extra:
        print(f"UNEXPECTED EXTRAS: {sorted(extra)}", file=sys.stderr)

    if not missing and not extra:
        print("PASS: tools/list matches expected set")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
