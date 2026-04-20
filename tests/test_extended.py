"""Unit tests for the extended PRD §5 MCP tools.

All yfinance / network calls are mocked — no live HTTP traffic.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pandas as pd
import pytest

from yfmcp.extended import download
from yfmcp.extended import get_calendar
from yfmcp.extended import get_fast_info
from yfmcp.extended import get_financials
from yfmcp.extended import get_history_advanced
from yfmcp.extended import get_holders
from yfmcp.extended import get_insider_transactions
from yfmcp.extended import get_options
from yfmcp.extended import get_recommendations


def _passthrough_to_thread() -> AsyncMock:
    """Return an AsyncMock for ``asyncio.to_thread`` that simply runs the callable."""

    async def _runner(func, *args, **kwargs):
        return func(*args, **kwargs)

    mock = AsyncMock()
    mock.side_effect = _runner
    return mock


# ---------------------------------------------------------------------------
# yfinance_download
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("yfmcp.extended.yf.download")
@patch("yfmcp.extended.asyncio.to_thread", new_callable=_passthrough_to_thread)
async def test_download_single_symbol(_mock_thread, mock_yf_download: MagicMock) -> None:
    df = pd.DataFrame(
        {
            "Open": [10.0, 11.0],
            "High": [11.0, 12.0],
            "Low": [9.5, 10.5],
            "Close": [10.5, 11.5],
            "Volume": [1000, 1500],
        },
        index=pd.date_range("2024-01-01", periods=2, freq="D"),
    )
    mock_yf_download.return_value = df

    result = await download(["AAPL"])
    data = json.loads(result)

    assert data["tickers"] == ["AAPL"]
    assert len(data["rows"]) == 2
    assert data["rows"][0]["Ticker"] == "AAPL"


@pytest.mark.asyncio
@patch("yfmcp.extended.yf.download")
@patch("yfmcp.extended.asyncio.to_thread", new_callable=_passthrough_to_thread)
async def test_download_multi_symbol(_mock_thread, mock_yf_download: MagicMock) -> None:
    idx = pd.date_range("2024-01-01", periods=2, freq="D")
    cols = pd.MultiIndex.from_product([["AAPL", "MSFT"], ["Open", "Close", "Volume"]])
    values = [
        [10.0, 11.0, 1000, 200.0, 201.0, 500],
        [11.0, 12.0, 1100, 201.0, 202.0, 600],
    ]
    df = pd.DataFrame(values, index=idx, columns=cols)
    mock_yf_download.return_value = df

    result = await download(["AAPL", "MSFT"])
    data = json.loads(result)

    tickers = {r["Ticker"] for r in data["rows"]}
    assert tickers == {"AAPL", "MSFT"}


@pytest.mark.asyncio
@patch("yfmcp.extended.yf.download")
@patch("yfmcp.extended.asyncio.to_thread", new_callable=_passthrough_to_thread)
async def test_download_empty(_mock_thread, mock_yf_download: MagicMock) -> None:
    mock_yf_download.return_value = pd.DataFrame()
    data = json.loads(await download(["BADSYM"]))
    assert data["error_code"] == "NO_DATA"


@pytest.mark.asyncio
async def test_download_invalid_date() -> None:
    data = json.loads(await download(["AAPL"], start="not-a-date"))
    assert data["error_code"] == "INVALID_PARAMS"


@pytest.mark.asyncio
@patch("yfmcp.extended.asyncio.to_thread", new_callable=_passthrough_to_thread)
@patch("yfmcp.extended.yf.download", side_effect=ConnectionError("boom"))
async def test_download_network_error(mock_dl, _mock_thread) -> None:
    data = json.loads(await download(["AAPL"]))
    assert data["error_code"] == "NETWORK_ERROR"


# ---------------------------------------------------------------------------
# yfinance_get_history_advanced
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("yfmcp.extended.yf.Ticker")
@patch("yfmcp.extended.asyncio.to_thread", new_callable=_passthrough_to_thread)
async def test_get_history_advanced_table(_mock_thread, mock_ticker: MagicMock) -> None:
    df = pd.DataFrame(
        {
            "Open": [10.0],
            "High": [11.0],
            "Low": [9.5],
            "Close": [10.5],
            "Volume": [1000],
        },
        index=pd.date_range("2024-01-01", periods=1, freq="D"),
    )
    mock_ticker.return_value = MagicMock(history=MagicMock(return_value=df))

    result = await get_history_advanced("AAPL", start="2024-01-01", end="2024-02-01")

    assert isinstance(result, str)
    assert "Open" in result and "Close" in result


@pytest.mark.asyncio
async def test_get_history_advanced_invalid_date() -> None:
    result = await get_history_advanced("AAPL", start="bad")
    data = json.loads(result)
    assert data["error_code"] == "INVALID_PARAMS"


@pytest.mark.asyncio
@patch("yfmcp.extended.yf.Ticker")
@patch("yfmcp.extended.asyncio.to_thread", new_callable=_passthrough_to_thread)
async def test_get_history_advanced_no_data(_mock_thread, mock_ticker: MagicMock) -> None:
    mock_ticker.return_value = MagicMock(history=MagicMock(return_value=pd.DataFrame()))
    result = await get_history_advanced("AAPL")
    data = json.loads(result)
    assert data["error_code"] == "NO_DATA"


# ---------------------------------------------------------------------------
# yfinance_get_financials
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("yfmcp.extended.yf.Ticker")
@patch("yfmcp.extended.asyncio.to_thread", new_callable=_passthrough_to_thread)
async def test_get_financials_income(_mock_thread, mock_ticker: MagicMock) -> None:
    df = pd.DataFrame(
        {pd.Timestamp("2024-12-31"): [1000, 200], pd.Timestamp("2023-12-31"): [900, 180]},
        index=["TotalRevenue", "NetIncome"],
    )
    mock_ticker.return_value = MagicMock(financials=df, quarterly_financials=df)

    result = await get_financials("AAPL", statement="income")
    data = json.loads(result)

    assert data["statement"] == "income"
    assert not data["quarterly"]
    assert isinstance(data["rows"], list) and len(data["rows"]) == 2


@pytest.mark.asyncio
async def test_get_financials_invalid_statement() -> None:
    # Bypass typing — runtime guard must respond gracefully.
    data = json.loads(await get_financials("AAPL", statement="bogus"))
    assert data["error_code"] == "INVALID_PARAMS"


@pytest.mark.asyncio
@patch("yfmcp.extended.yf.Ticker")
@patch("yfmcp.extended.asyncio.to_thread", new_callable=_passthrough_to_thread)
async def test_get_financials_empty(_mock_thread, mock_ticker: MagicMock) -> None:
    mock_ticker.return_value = MagicMock(balance_sheet=pd.DataFrame(), quarterly_balance_sheet=pd.DataFrame())
    data = json.loads(await get_financials("AAPL", statement="balance"))
    assert data["error_code"] == "NO_DATA"


# ---------------------------------------------------------------------------
# yfinance_get_options
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("yfmcp.extended.yf.Ticker")
@patch("yfmcp.extended.asyncio.to_thread", new_callable=_passthrough_to_thread)
async def test_get_options_list_only(_mock_thread, mock_ticker: MagicMock) -> None:
    mock_ticker.return_value = MagicMock(options=("2024-12-20", "2025-01-17"))
    data = json.loads(await get_options("AAPL"))
    assert data["expirations"] == ["2024-12-20", "2025-01-17"]


@pytest.mark.asyncio
@patch("yfmcp.extended.yf.Ticker")
@patch("yfmcp.extended.asyncio.to_thread", new_callable=_passthrough_to_thread)
async def test_get_options_chain(_mock_thread, mock_ticker: MagicMock) -> None:
    calls = pd.DataFrame({"strike": [100, 110], "lastPrice": [5.0, 2.5]})
    puts = pd.DataFrame({"strike": [100, 110], "lastPrice": [3.0, 6.0]})
    chain = MagicMock(calls=calls, puts=puts)
    mock_ticker.return_value = MagicMock(options=("2024-12-20",), option_chain=MagicMock(return_value=chain))

    data = json.loads(await get_options("AAPL", expiration="2024-12-20"))
    assert len(data["calls"]) == 2
    assert len(data["puts"]) == 2


@pytest.mark.asyncio
@patch("yfmcp.extended.yf.Ticker")
@patch("yfmcp.extended.asyncio.to_thread", new_callable=_passthrough_to_thread)
async def test_get_options_unknown_expiration(_mock_thread, mock_ticker: MagicMock) -> None:
    mock_ticker.return_value = MagicMock(options=("2024-12-20",))
    data = json.loads(await get_options("AAPL", expiration="2025-06-20"))
    assert data["error_code"] == "INVALID_PARAMS"


@pytest.mark.asyncio
async def test_get_options_invalid_date() -> None:
    data = json.loads(await get_options("AAPL", expiration="bad"))
    assert data["error_code"] == "INVALID_PARAMS"


@pytest.mark.asyncio
@patch("yfmcp.extended.yf.Ticker")
@patch("yfmcp.extended.asyncio.to_thread", new_callable=_passthrough_to_thread)
async def test_get_options_no_data(_mock_thread, mock_ticker: MagicMock) -> None:
    mock_ticker.return_value = MagicMock(options=())
    data = json.loads(await get_options("AAPL"))
    assert data["error_code"] == "NO_DATA"


# ---------------------------------------------------------------------------
# yfinance_get_recommendations / calendar / insider / fast_info
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("yfmcp.extended.yf.Ticker")
@patch("yfmcp.extended.asyncio.to_thread", new_callable=_passthrough_to_thread)
async def test_get_recommendations_success(_mock_thread, mock_ticker: MagicMock) -> None:
    df = pd.DataFrame(
        {
            "Firm": ["Goldman", "Morgan"],
            "Action": ["init", "up"],
            "From Grade": ["", "Hold"],
            "To Grade": ["Buy", "Buy"],
        },
        index=pd.date_range("2024-01-01", periods=2, freq="D"),
    )
    mock_ticker.return_value = MagicMock(recommendations=df)
    data = json.loads(await get_recommendations("AAPL"))
    assert data["symbol"] == "AAPL"
    assert len(data["rows"]) == 2


@pytest.mark.asyncio
@patch("yfmcp.extended.yf.Ticker")
@patch("yfmcp.extended.asyncio.to_thread", new_callable=_passthrough_to_thread)
async def test_get_recommendations_empty(_mock_thread, mock_ticker: MagicMock) -> None:
    mock_ticker.return_value = MagicMock(recommendations=pd.DataFrame())
    data = json.loads(await get_recommendations("AAPL"))
    assert data["error_code"] == "NO_DATA"


@pytest.mark.asyncio
@patch("yfmcp.extended.yf.Ticker")
@patch("yfmcp.extended.asyncio.to_thread", new_callable=_passthrough_to_thread)
async def test_get_calendar_dict(_mock_thread, mock_ticker: MagicMock) -> None:
    mock_ticker.return_value = MagicMock(calendar={"Earnings Date": ["2025-01-30"], "Earnings Average": [2.18]})
    data = json.loads(await get_calendar("AAPL"))
    assert "calendar" in data and "Earnings Date" in data["calendar"]


@pytest.mark.asyncio
@patch("yfmcp.extended.yf.Ticker")
@patch("yfmcp.extended.asyncio.to_thread", new_callable=_passthrough_to_thread)
async def test_get_calendar_dataframe(_mock_thread, mock_ticker: MagicMock) -> None:
    df = pd.DataFrame({"Earnings Date": [pd.Timestamp("2025-01-30")], "Earnings Average": [2.18]})
    mock_ticker.return_value = MagicMock(calendar=df)
    data = json.loads(await get_calendar("AAPL"))
    assert "rows" in data and len(data["rows"]) == 1


@pytest.mark.asyncio
@patch("yfmcp.extended.yf.Ticker")
@patch("yfmcp.extended.asyncio.to_thread", new_callable=_passthrough_to_thread)
async def test_get_calendar_none(_mock_thread, mock_ticker: MagicMock) -> None:
    mock_ticker.return_value = MagicMock(calendar=None)
    data = json.loads(await get_calendar("AAPL"))
    assert data["error_code"] == "NO_DATA"


@pytest.mark.asyncio
@patch("yfmcp.extended.yf.Ticker")
@patch("yfmcp.extended.asyncio.to_thread", new_callable=_passthrough_to_thread)
async def test_get_holders_institutional(_mock_thread, mock_ticker: MagicMock) -> None:
    df = pd.DataFrame({"Holder": ["Vanguard", "BlackRock"], "Shares": [1000, 900]})
    mock_ticker.return_value = MagicMock(institutional_holders=df)
    data = json.loads(await get_holders("AAPL", holder_type="institutional"))
    assert data["holder_type"] == "institutional"
    assert len(data["rows"]) == 2


@pytest.mark.asyncio
async def test_get_holders_invalid_type() -> None:
    data = json.loads(await get_holders("AAPL", holder_type="bogus"))
    assert data["error_code"] == "INVALID_PARAMS"


@pytest.mark.asyncio
@patch("yfmcp.extended.yf.Ticker")
@patch("yfmcp.extended.asyncio.to_thread", new_callable=_passthrough_to_thread)
async def test_get_insider_transactions(_mock_thread, mock_ticker: MagicMock) -> None:
    df = pd.DataFrame({"Insider": ["Tim Cook"], "Shares": [50000], "Transaction": ["Sale"]})
    mock_ticker.return_value = MagicMock(insider_transactions=df)
    data = json.loads(await get_insider_transactions("AAPL"))
    assert len(data["rows"]) == 1


@pytest.mark.asyncio
@patch("yfmcp.extended.yf.Ticker")
@patch("yfmcp.extended.asyncio.to_thread", new_callable=_passthrough_to_thread)
async def test_get_insider_transactions_empty(_mock_thread, mock_ticker: MagicMock) -> None:
    mock_ticker.return_value = MagicMock(insider_transactions=pd.DataFrame())
    data = json.loads(await get_insider_transactions("AAPL"))
    assert data["error_code"] == "NO_DATA"


@pytest.mark.asyncio
@patch("yfmcp.extended.yf.Ticker")
@patch("yfmcp.extended.asyncio.to_thread", new_callable=_passthrough_to_thread)
async def test_get_fast_info(_mock_thread, mock_ticker: MagicMock) -> None:
    fast = MagicMock()
    snapshot = {"last_price": 175.5, "market_cap": 2.7e12, "currency": "USD"}
    fast.keys = MagicMock(return_value=list(snapshot.keys()))
    fast.__getitem__ = MagicMock(side_effect=snapshot.__getitem__)
    mock_ticker.return_value = MagicMock(fast_info=fast)

    data = json.loads(await get_fast_info("AAPL"))
    assert data["fast_info"]["last_price"] == 175.5
    assert data["fast_info"]["currency"] == "USD"


@pytest.mark.asyncio
@patch("yfmcp.extended.yf.Ticker")
@patch("yfmcp.extended.asyncio.to_thread", new_callable=_passthrough_to_thread)
async def test_get_fast_info_none(_mock_thread, mock_ticker: MagicMock) -> None:
    mock_ticker.return_value = MagicMock(fast_info=None)
    data = json.loads(await get_fast_info("AAPL"))
    assert data["error_code"] == "NO_DATA"


# ---------------------------------------------------------------------------
# Tool registration smoke test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extended_tools_registered() -> None:
    """Importing extended must register the new tools on the shared FastMCP instance."""
    import yfmcp.extended  # noqa: F401  (force registration)
    from yfmcp.server import mcp

    listed = await mcp.list_tools()
    names = {t.name for t in listed}

    expected = {
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
    missing = expected - names
    assert not missing, f"missing tools: {missing}"
