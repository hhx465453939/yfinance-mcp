"""Extended MCP tools — additional yfinance capabilities (PRD §5).

Importing this module registers the following tools on the shared FastMCP
instance defined in ``yfmcp.server``:

- ``yfinance_download``                 batch OHLCV via ``yf.download``
- ``yfinance_get_history_advanced``     ``Ticker.history`` with start/end + flags
- ``yfinance_get_financials``           income / balance / cashflow (annual or quarterly)
- ``yfinance_get_options``              option expirations + option chain by date
- ``yfinance_get_recommendations``      analyst recommendations history
- ``yfinance_get_calendar``             earnings / dividend calendar
- ``yfinance_get_holders``              major / institutional / mutual fund holders
- ``yfinance_get_insider_transactions`` insider transactions
- ``yfinance_get_fast_info``            lightweight quote snapshot

All blocking yfinance calls go through ``asyncio.to_thread``. Errors are
returned as structured JSON via ``create_error_response``.
"""

from __future__ import annotations

import asyncio
from datetime import date
from datetime import datetime
from typing import Annotated
from typing import Literal

import pandas as pd
import yfinance as yf
from loguru import logger
from mcp.types import ImageContent
from mcp.types import ToolAnnotations
from pydantic import Field

from yfmcp.chart import generate_chart
from yfmcp.server import mcp
from yfmcp.throttle import make_ticker, throttled_download
from yfmcp.types import ChartType
from yfmcp.types import Interval
from yfmcp.types import Period
from yfmcp.utils import create_error_response
from yfmcp.utils import dump_json

StatementType = Literal["income", "balance", "cashflow"]
HolderType = Literal["major", "institutional", "mutualfund"]

_DATE_FORMAT = "%Y-%m-%d"

_READONLY_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)


def _validate_date(value: str | None, field: str) -> tuple[date | None, str | None]:
    """Parse YYYY-MM-DD string or return an INVALID_PARAMS error message."""
    if value is None:
        return None, None
    try:
        return datetime.strptime(value, _DATE_FORMAT).date(), None
    except ValueError:
        return None, f"Invalid {field} '{value}'. Expected ISO format YYYY-MM-DD (e.g. 2024-01-15)."


def _df_to_records(df: pd.DataFrame | None) -> list[dict] | None:
    """Convert a DataFrame to JSON-safe dict records.

    - Resets index so that any DatetimeIndex / labeled index becomes a column.
    - Coerces all column labels (including MultiIndex tuples and Timestamps) to ``str``
      so the result is safe to feed to ``json.dumps``.
    """
    if df is None or df.empty:
        return None
    df = df.reset_index()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = ["__".join([str(c) for c in col if c not in (None, "")]) for col in df.columns]
    else:
        df.columns = [str(c) for c in df.columns]
    return df.to_dict(orient="records")


# ---------------------------------------------------------------------------
# yfinance_download — batch OHLCV
# ---------------------------------------------------------------------------


def _flatten_download_frame(df: pd.DataFrame, symbols: list[str]) -> list[dict]:
    """Flatten a (possibly MultiIndex) ``yf.download`` frame to per-row records with Ticker."""
    rows: list[dict] = []
    if isinstance(df.columns, pd.MultiIndex):
        for sym in symbols:
            if sym not in df.columns.get_level_values(0):
                continue
            sub = df[sym].dropna(how="all").reset_index()
            sub["Ticker"] = sym
            rows.extend(sub.to_dict(orient="records"))
    else:
        sub = df.dropna(how="all").reset_index()
        sub["Ticker"] = symbols[0]
        rows.extend(sub.to_dict(orient="records"))
    return rows


def _build_download_kwargs(
    symbols: list[str],
    period: Period,
    interval: Interval,
    start: str | None,
    end: str | None,
    auto_adjust: bool,
    prepost: bool,
) -> dict:
    kwargs: dict = {
        "tickers": symbols,
        "interval": interval,
        "auto_adjust": auto_adjust,
        "prepost": prepost,
        "progress": False,
        "group_by": "ticker",
        "threads": True,
    }
    if start or end:
        if start:
            kwargs["start"] = start
        if end:
            kwargs["end"] = end
    else:
        kwargs["period"] = period
    return kwargs


@mcp.tool(name="yfinance_download", annotations=_READONLY_ANNOTATIONS)
async def download(
    symbols: Annotated[
        list[str],
        Field(description="List of ticker symbols, e.g. ['AAPL', 'MSFT', '600519.SS']", min_length=1, max_length=50),
    ],
    period: Annotated[Period, Field(description="Time range when start/end omitted (default '1mo')")] = "1mo",
    interval: Annotated[Interval, Field(description="Bar interval (default '1d')")] = "1d",
    start: Annotated[str | None, Field(description="ISO date YYYY-MM-DD (overrides period)")] = None,
    end: Annotated[str | None, Field(description="ISO date YYYY-MM-DD (exclusive)")] = None,
    auto_adjust: Annotated[bool, Field(description="Adjust OHLC for splits/dividends (default True)")] = True,
    prepost: Annotated[bool, Field(description="Include pre/post market data (default False)")] = False,
) -> str:
    """Batch download historical OHLCV for multiple tickers via ``yf.download``.

    Returns JSON: ``{"tickers": [...], "rows": [{Date, Ticker, Open, High, Low, Close, Volume, ...}, ...]}``.
    """
    _, err = _validate_date(start, "start")
    if err:
        return create_error_response(err, error_code="INVALID_PARAMS", details={"start": start})
    _, err = _validate_date(end, "end")
    if err:
        return create_error_response(err, error_code="INVALID_PARAMS", details={"end": end})

    kwargs = _build_download_kwargs(symbols, period, interval, start, end, auto_adjust, prepost)

    try:
        df = await throttled_download(**kwargs)
    except (ConnectionError, TimeoutError, OSError) as exc:
        return create_error_response(
            f"Network error while downloading {symbols}. Check your internet connection and try again.",
            error_code="NETWORK_ERROR",
            details={"symbols": symbols, "exception": str(exc)},
        )
    except Exception as exc:
        return create_error_response(
            f"Failed to download {symbols}. Verify symbols / period / interval combination.",
            error_code="API_ERROR",
            details={"symbols": symbols, "exception": str(exc)},
        )

    if df is None or df.empty:
        return create_error_response(
            f"No data returned for {symbols}.",
            error_code="NO_DATA",
            details={"symbols": symbols, "period": period, "interval": interval},
        )

    rows = _flatten_download_frame(df, symbols)
    if not rows:
        return create_error_response(
            f"All symbols returned empty rows for {symbols}.",
            error_code="NO_DATA",
            details={"symbols": symbols},
        )

    return dump_json({"tickers": symbols, "rows": rows})


# ---------------------------------------------------------------------------
# yfinance_get_history_advanced — Ticker.history with start/end + flags
# ---------------------------------------------------------------------------


@mcp.tool(name="yfinance_get_history_advanced", annotations=_READONLY_ANNOTATIONS)
async def get_history_advanced(
    symbol: Annotated[str, Field(description="Ticker symbol")],
    start: Annotated[str | None, Field(description="ISO date YYYY-MM-DD (overrides period)")] = None,
    end: Annotated[str | None, Field(description="ISO date YYYY-MM-DD (exclusive)")] = None,
    period: Annotated[Period, Field(description="Used when start/end are omitted (default '1mo')")] = "1mo",
    interval: Annotated[Interval, Field(description="Bar interval (default '1d')")] = "1d",
    auto_adjust: Annotated[bool, Field(description="Adjust OHLC for splits/dividends (default True)")] = True,
    actions: Annotated[bool, Field(description="Include Dividends/Stock Splits columns (default True)")] = True,
    prepost: Annotated[bool, Field(description="Include pre/post market data (default False)")] = False,
    repair: Annotated[bool, Field(description="Heuristically repair bad ticks (default False)")] = False,
    chart_type: Annotated[ChartType | None, Field(description="Optional chart; omit for Markdown table")] = None,
) -> str | ImageContent:
    """``Ticker.history`` with full parameter surface (PRD §5)."""
    _, err = _validate_date(start, "start")
    if err:
        return create_error_response(err, error_code="INVALID_PARAMS", details={"start": start})
    _, err = _validate_date(end, "end")
    if err:
        return create_error_response(err, error_code="INVALID_PARAMS", details={"end": end})

    history_kwargs: dict = {
        "interval": interval,
        "auto_adjust": auto_adjust,
        "actions": actions,
        "prepost": prepost,
        "repair": repair,
        "rounding": True,
    }
    if start or end:
        if start:
            history_kwargs["start"] = start
        if end:
            history_kwargs["end"] = end
    else:
        history_kwargs["period"] = period

    try:
        ticker = await make_ticker(symbol)
        df = await asyncio.to_thread(ticker.history, **history_kwargs)
    except (ConnectionError, TimeoutError, OSError) as exc:
        return create_error_response(
            f"Network error while fetching history for '{symbol}'.",
            error_code="NETWORK_ERROR",
            details={"symbol": symbol, "exception": str(exc)},
        )
    except Exception as exc:
        return create_error_response(
            f"Failed to fetch history for '{symbol}'. Verify parameters.",
            error_code="API_ERROR",
            details={"symbol": symbol, "exception": str(exc)},
        )

    if df is None or df.empty:
        return create_error_response(
            f"No history for '{symbol}' with given parameters.",
            error_code="NO_DATA",
            details={
                "symbol": symbol,
                "start": start,
                "end": end,
                "period": period,
                "interval": interval,
            },
        )

    if chart_type is None:
        return df.to_markdown()
    return generate_chart(symbol=symbol, df=df, chart_type=chart_type)


# ---------------------------------------------------------------------------
# yfinance_get_financials — income/balance/cashflow (annual or quarterly)
# ---------------------------------------------------------------------------


_STATEMENT_ATTR_MAP = {
    "income": ("financials", "quarterly_financials"),
    "balance": ("balance_sheet", "quarterly_balance_sheet"),
    "cashflow": ("cashflow", "quarterly_cashflow"),
}


@mcp.tool(name="yfinance_get_financials", annotations=_READONLY_ANNOTATIONS)
async def get_financials(
    symbol: Annotated[str, Field(description="Ticker symbol")],
    statement: Annotated[
        StatementType,
        Field(description="Statement: 'income', 'balance', or 'cashflow'"),
    ],
    quarterly: Annotated[bool, Field(description="True for quarterly, False for annual (default)")] = False,
) -> str:
    """Return one of the three financial statements as JSON records keyed by line item."""
    if statement not in _STATEMENT_ATTR_MAP:
        return create_error_response(
            f"Invalid statement '{statement}'. Valid: income / balance / cashflow.",
            error_code="INVALID_PARAMS",
            details={"statement": statement},
        )

    attr_annual, attr_quarterly = _STATEMENT_ATTR_MAP[statement]
    attr = attr_quarterly if quarterly else attr_annual

    try:
        ticker = await make_ticker(symbol)
        df = await asyncio.to_thread(lambda: getattr(ticker, attr))
    except (ConnectionError, TimeoutError, OSError) as exc:
        return create_error_response(
            f"Network error while fetching {statement} statement for '{symbol}'.",
            error_code="NETWORK_ERROR",
            details={"symbol": symbol, "statement": statement, "exception": str(exc)},
        )
    except Exception as exc:
        return create_error_response(
            f"Failed to fetch {statement} statement for '{symbol}'.",
            error_code="API_ERROR",
            details={"symbol": symbol, "statement": statement, "exception": str(exc)},
        )

    if df is None or (hasattr(df, "empty") and df.empty):
        return create_error_response(
            f"No {statement} data for '{symbol}'.",
            error_code="NO_DATA",
            details={"symbol": symbol, "statement": statement, "quarterly": quarterly},
        )

    return dump_json(
        {
            "symbol": symbol,
            "statement": statement,
            "quarterly": quarterly,
            "rows": _df_to_records(df),
        }
    )


# ---------------------------------------------------------------------------
# yfinance_get_options — expirations + option chain
# ---------------------------------------------------------------------------


@mcp.tool(name="yfinance_get_options", annotations=_READONLY_ANNOTATIONS)
async def get_options(
    symbol: Annotated[str, Field(description="Underlying ticker symbol")],
    expiration: Annotated[
        str | None,
        Field(description="ISO date YYYY-MM-DD; omit to list available expirations only"),
    ] = None,
) -> str:
    """List option expirations or fetch the option chain (calls + puts) for a date."""
    if expiration is not None:
        _, err = _validate_date(expiration, "expiration")
        if err:
            return create_error_response(err, error_code="INVALID_PARAMS", details={"expiration": expiration})

    try:
        ticker = await make_ticker(symbol)
        expirations = await asyncio.to_thread(lambda: list(getattr(ticker, "options", []) or []))
    except (ConnectionError, TimeoutError, OSError) as exc:
        return create_error_response(
            f"Network error while fetching options for '{symbol}'.",
            error_code="NETWORK_ERROR",
            details={"symbol": symbol, "exception": str(exc)},
        )
    except Exception as exc:
        return create_error_response(
            f"Failed to fetch options for '{symbol}'.",
            error_code="API_ERROR",
            details={"symbol": symbol, "exception": str(exc)},
        )

    if not expirations:
        return create_error_response(
            f"No options listed for '{symbol}' (may not be optionable).",
            error_code="NO_DATA",
            details={"symbol": symbol},
        )

    if expiration is None:
        return dump_json({"symbol": symbol, "expirations": expirations})

    if expiration not in expirations:
        return create_error_response(
            f"Expiration '{expiration}' not in available list for '{symbol}'.",
            error_code="INVALID_PARAMS",
            details={"symbol": symbol, "expiration": expiration, "available": expirations},
        )

    try:
        chain = await asyncio.to_thread(ticker.option_chain, expiration)
    except Exception as exc:
        return create_error_response(
            f"Failed to fetch option chain for '{symbol}' @ {expiration}.",
            error_code="API_ERROR",
            details={"symbol": symbol, "expiration": expiration, "exception": str(exc)},
        )

    return dump_json(
        {
            "symbol": symbol,
            "expiration": expiration,
            "calls": _df_to_records(chain.calls) or [],
            "puts": _df_to_records(chain.puts) or [],
        }
    )


# ---------------------------------------------------------------------------
# yfinance_get_recommendations
# ---------------------------------------------------------------------------


@mcp.tool(name="yfinance_get_recommendations", annotations=_READONLY_ANNOTATIONS)
async def get_recommendations(
    symbol: Annotated[str, Field(description="Ticker symbol")],
) -> str:
    """Analyst recommendation history (broker, action, from/to grade, etc.)."""
    try:
        ticker = await make_ticker(symbol)
        df = await asyncio.to_thread(lambda: ticker.recommendations)
    except (ConnectionError, TimeoutError, OSError) as exc:
        return create_error_response(
            f"Network error while fetching recommendations for '{symbol}'.",
            error_code="NETWORK_ERROR",
            details={"symbol": symbol, "exception": str(exc)},
        )
    except Exception as exc:
        return create_error_response(
            f"Failed to fetch recommendations for '{symbol}'.",
            error_code="API_ERROR",
            details={"symbol": symbol, "exception": str(exc)},
        )

    rows = _df_to_records(df)
    if not rows:
        return create_error_response(
            f"No recommendations available for '{symbol}'.",
            error_code="NO_DATA",
            details={"symbol": symbol},
        )

    return dump_json({"symbol": symbol, "rows": rows})


# ---------------------------------------------------------------------------
# yfinance_get_calendar
# ---------------------------------------------------------------------------


@mcp.tool(name="yfinance_get_calendar", annotations=_READONLY_ANNOTATIONS)
async def get_calendar(
    symbol: Annotated[str, Field(description="Ticker symbol")],
) -> str:
    """Earnings / dividend calendar for the symbol."""
    try:
        ticker = await make_ticker(symbol)
        cal = await asyncio.to_thread(lambda: ticker.calendar)
    except (ConnectionError, TimeoutError, OSError) as exc:
        return create_error_response(
            f"Network error while fetching calendar for '{symbol}'.",
            error_code="NETWORK_ERROR",
            details={"symbol": symbol, "exception": str(exc)},
        )
    except Exception as exc:
        return create_error_response(
            f"Failed to fetch calendar for '{symbol}'.",
            error_code="API_ERROR",
            details={"symbol": symbol, "exception": str(exc)},
        )

    if cal is None:
        return create_error_response(
            f"No calendar data for '{symbol}'.",
            error_code="NO_DATA",
            details={"symbol": symbol},
        )

    if isinstance(cal, pd.DataFrame):
        rows = _df_to_records(cal)
        if not rows:
            return create_error_response(
                f"No calendar data for '{symbol}'.",
                error_code="NO_DATA",
                details={"symbol": symbol},
            )
        return dump_json({"symbol": symbol, "rows": rows})

    if isinstance(cal, dict):
        if not cal:
            return create_error_response(
                f"No calendar data for '{symbol}'.",
                error_code="NO_DATA",
                details={"symbol": symbol},
            )
        return dump_json({"symbol": symbol, "calendar": cal})

    return dump_json({"symbol": symbol, "calendar": cal})


# ---------------------------------------------------------------------------
# yfinance_get_holders
# ---------------------------------------------------------------------------


_HOLDER_ATTR_MAP = {
    "major": "major_holders",
    "institutional": "institutional_holders",
    "mutualfund": "mutualfund_holders",
}


@mcp.tool(name="yfinance_get_holders", annotations=_READONLY_ANNOTATIONS)
async def get_holders(
    symbol: Annotated[str, Field(description="Ticker symbol")],
    holder_type: Annotated[
        HolderType,
        Field(description="Type: 'major', 'institutional', or 'mutualfund'"),
    ] = "institutional",
) -> str:
    """Holder breakdown (major / institutional / mutual fund)."""
    attr = _HOLDER_ATTR_MAP.get(holder_type)
    if attr is None:
        return create_error_response(
            f"Invalid holder_type '{holder_type}'. Valid: major / institutional / mutualfund.",
            error_code="INVALID_PARAMS",
            details={"holder_type": holder_type},
        )

    try:
        ticker = await make_ticker(symbol)
        df = await asyncio.to_thread(lambda: getattr(ticker, attr))
    except (ConnectionError, TimeoutError, OSError) as exc:
        return create_error_response(
            f"Network error while fetching {holder_type} holders for '{symbol}'.",
            error_code="NETWORK_ERROR",
            details={"symbol": symbol, "holder_type": holder_type, "exception": str(exc)},
        )
    except Exception as exc:
        return create_error_response(
            f"Failed to fetch {holder_type} holders for '{symbol}'.",
            error_code="API_ERROR",
            details={"symbol": symbol, "holder_type": holder_type, "exception": str(exc)},
        )

    rows = _df_to_records(df)
    if not rows:
        return create_error_response(
            f"No {holder_type} holders data for '{symbol}'.",
            error_code="NO_DATA",
            details={"symbol": symbol, "holder_type": holder_type},
        )

    return dump_json({"symbol": symbol, "holder_type": holder_type, "rows": rows})


# ---------------------------------------------------------------------------
# yfinance_get_insider_transactions
# ---------------------------------------------------------------------------


@mcp.tool(name="yfinance_get_insider_transactions", annotations=_READONLY_ANNOTATIONS)
async def get_insider_transactions(
    symbol: Annotated[str, Field(description="Ticker symbol")],
) -> str:
    """Insider transaction history (officers/directors filings)."""
    try:
        ticker = await make_ticker(symbol)
        df = await asyncio.to_thread(lambda: ticker.insider_transactions)
    except (ConnectionError, TimeoutError, OSError) as exc:
        return create_error_response(
            f"Network error while fetching insider transactions for '{symbol}'.",
            error_code="NETWORK_ERROR",
            details={"symbol": symbol, "exception": str(exc)},
        )
    except Exception as exc:
        return create_error_response(
            f"Failed to fetch insider transactions for '{symbol}'.",
            error_code="API_ERROR",
            details={"symbol": symbol, "exception": str(exc)},
        )

    rows = _df_to_records(df)
    if not rows:
        return create_error_response(
            f"No insider transactions for '{symbol}'.",
            error_code="NO_DATA",
            details={"symbol": symbol},
        )

    return dump_json({"symbol": symbol, "rows": rows})


# ---------------------------------------------------------------------------
# yfinance_get_fast_info
# ---------------------------------------------------------------------------


@mcp.tool(name="yfinance_get_fast_info", annotations=_READONLY_ANNOTATIONS)
async def get_fast_info(
    symbol: Annotated[str, Field(description="Ticker symbol")],
) -> str:
    """Lightweight quote snapshot (last price, market cap, day range, etc.)."""
    try:
        ticker = await make_ticker(symbol)
        fast = await asyncio.to_thread(lambda: ticker.fast_info)
    except (ConnectionError, TimeoutError, OSError) as exc:
        return create_error_response(
            f"Network error while fetching fast_info for '{symbol}'.",
            error_code="NETWORK_ERROR",
            details={"symbol": symbol, "exception": str(exc)},
        )
    except Exception as exc:
        return create_error_response(
            f"Failed to fetch fast_info for '{symbol}'.",
            error_code="API_ERROR",
            details={"symbol": symbol, "exception": str(exc)},
        )

    if fast is None:
        return create_error_response(
            f"No fast_info for '{symbol}'.",
            error_code="NO_DATA",
            details={"symbol": symbol},
        )

    snapshot: dict = {}
    try:
        keys = list(fast.keys())
    except Exception:
        keys = [
            "last_price",
            "previous_close",
            "open",
            "day_high",
            "day_low",
            "fifty_day_average",
            "two_hundred_day_average",
            "year_high",
            "year_low",
            "year_change",
            "market_cap",
            "shares",
            "currency",
            "exchange",
            "quote_type",
            "timezone",
        ]

    for key in keys:
        try:
            value = fast[key] if hasattr(fast, "__getitem__") else getattr(fast, key)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("fast_info key {} unavailable: {}", key, exc)
            continue
        snapshot[key] = value

    if not snapshot:
        return create_error_response(
            f"fast_info for '{symbol}' returned no readable fields.",
            error_code="NO_DATA",
            details={"symbol": symbol},
        )

    return dump_json({"symbol": symbol, "fast_info": snapshot})
