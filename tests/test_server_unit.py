"""Unit tests for server.py functions with mocks."""

import json
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pandas as pd
import pytest

from yfmcp.server import _build_financials_response
from yfmcp.server import get_financials
from yfmcp.server import get_price_history
from yfmcp.server import get_top_companies
from yfmcp.server import get_top_etfs
from yfmcp.server import get_top_growth_companies
from yfmcp.server import get_top_mutual_funds
from yfmcp.server import get_top_performing_companies


def _financials_df(rows: dict[str, list[int]]) -> pd.DataFrame:
    """Build a yfinance-shaped financial statement DataFrame."""
    return pd.DataFrame(
        rows,
        index=[pd.Timestamp("2024-12-31"), pd.Timestamp("2023-12-31")],
        dtype=object,
    ).T


async def _run_to_thread(func, *args, **kwargs):
    if callable(func):
        return func(*args, **kwargs)
    return func


class _FinancialsReadErrorTicker:
    @property
    def income_stmt(self):
        raise RuntimeError("statement read failed")


def test_build_financials_response_with_all_sections() -> None:
    """Test building a financials response with all supported statement sections."""
    income_stmt = _financials_df(
        {
            "Total Revenue": [1000, 900],
            "Net Income": [120, 100],
            "Unsupported Income Row": [1, 2],
        }
    )
    balance_sheet = _financials_df(
        {
            "Total Assets": [5000, 4500],
            "Total Debt": [800, 750],
            "Unsupported Balance Row": [3, 4],
        }
    )
    cash_flow = _financials_df(
        {
            "Operating Cash Flow": [300, 280],
            "Free Cash Flow": [200, 180],
            "Unsupported Cash Flow Row": [5, 6],
        }
    )

    result = _build_financials_response(income_stmt, balance_sheet, cash_flow)

    assert set(result) == {"income_statement", "balance_sheet", "cash_flow"}
    assert result["income_statement"]["Total Revenue"]["2024-12-31"] == 1000
    assert result["income_statement"]["Net Income"]["2023-12-31"] == 100
    assert "Unsupported Income Row" not in result["income_statement"]
    assert result["balance_sheet"]["Total Assets"]["2024-12-31"] == 5000
    assert result["balance_sheet"]["Total Debt"]["2023-12-31"] == 750
    assert "Unsupported Balance Row" not in result["balance_sheet"]
    assert result["cash_flow"]["Operating Cash Flow"]["2024-12-31"] == 300
    assert result["cash_flow"]["Free Cash Flow"]["2023-12-31"] == 180
    assert "Unsupported Cash Flow Row" not in result["cash_flow"]


def test_build_financials_response_ignores_none_and_empty_dataframes() -> None:
    """Test that missing or empty statements do not produce response sections."""
    empty_df = pd.DataFrame()
    income_stmt = _financials_df({"EBIT": [100, 90]})

    partial_result = _build_financials_response(income_stmt, None, empty_df)
    empty_result = _build_financials_response(None, empty_df, None)

    assert set(partial_result) == {"income_statement"}
    assert partial_result["income_statement"]["EBIT"]["2024-12-31"] == 100
    assert empty_result == {}


@pytest.mark.asyncio
@patch("yfmcp.server.yf.Ticker")
@patch("yfmcp.server.asyncio.to_thread")
async def test_get_financials_annual_success(mock_to_thread: AsyncMock, mock_ticker: MagicMock) -> None:
    """Test annual financials retrieval."""
    mock_ticker_obj = MagicMock()
    mock_ticker_obj.income_stmt = _financials_df({"Total Revenue": [1000, 900]})
    mock_ticker_obj.balance_sheet = _financials_df({"Total Assets": [5000, 4500]})
    mock_ticker_obj.cashflow = _financials_df({"Operating Cash Flow": [300, 280]})
    mock_ticker.return_value = mock_ticker_obj
    mock_to_thread.side_effect = _run_to_thread

    result = await get_financials("AAPL", "annual")
    data = json.loads(result)

    assert data["income_statement"]["Total Revenue"]["2024-12-31"] == 1000
    assert data["balance_sheet"]["Total Assets"]["2023-12-31"] == 4500
    assert data["cash_flow"]["Operating Cash Flow"]["2024-12-31"] == 300


@pytest.mark.asyncio
@patch("yfmcp.server.yf.Ticker")
@patch("yfmcp.server.asyncio.to_thread")
async def test_get_financials_quarterly_success(mock_to_thread: AsyncMock, mock_ticker: MagicMock) -> None:
    """Test quarterly financials retrieval."""
    mock_ticker_obj = MagicMock()
    mock_ticker_obj.quarterly_income_stmt = _financials_df({"Operating Income": [400, 350]})
    mock_ticker_obj.quarterly_balance_sheet = _financials_df({"Stockholders Equity": [2200, 2100]})
    mock_ticker_obj.quarterly_cashflow = _financials_df({"Free Cash Flow": [150, 125]})
    mock_ticker.return_value = mock_ticker_obj
    mock_to_thread.side_effect = _run_to_thread

    result = await get_financials("MSFT", "quarterly")
    data = json.loads(result)

    assert data["income_statement"]["Operating Income"]["2024-12-31"] == 400
    assert data["balance_sheet"]["Stockholders Equity"]["2023-12-31"] == 2100
    assert data["cash_flow"]["Free Cash Flow"]["2024-12-31"] == 150


@pytest.mark.asyncio
@patch("yfmcp.server.yf.Ticker")
@patch("yfmcp.server.asyncio.to_thread")
async def test_get_financials_ttm_success_only_income_statement(
    mock_to_thread: AsyncMock, mock_ticker: MagicMock
) -> None:
    """Test TTM financials retrieval only returns income statement data."""
    mock_ticker_obj = MagicMock()
    mock_ticker_obj.ttm_income_stmt = _financials_df({"EBITDA": [700, 650]})
    mock_ticker.return_value = mock_ticker_obj
    mock_to_thread.side_effect = _run_to_thread

    result = await get_financials("NVDA", "ttm")
    data = json.loads(result)

    assert set(data) == {"income_statement"}
    assert data["income_statement"]["EBITDA"]["2024-12-31"] == 700


@pytest.mark.asyncio
@patch("yfmcp.server.yf.Ticker")
@patch("yfmcp.server.asyncio.to_thread")
async def test_get_financials_invalid_frequency(mock_to_thread: AsyncMock, mock_ticker: MagicMock) -> None:
    """Test invalid financials frequency returns structured parameter error."""
    mock_ticker.return_value = MagicMock()
    mock_to_thread.side_effect = _run_to_thread

    result = await get_financials("AAPL", "monthly")
    data = json.loads(result)

    assert data["error_code"] == "INVALID_PARAMS"
    assert data["details"]["frequency"] == "monthly"
    assert data["details"]["valid_options"] == ["annual", "quarterly", "ttm"]


@pytest.mark.asyncio
@patch("yfmcp.server.yf.Ticker")
@patch("yfmcp.server.asyncio.to_thread")
async def test_get_financials_no_data(mock_to_thread: AsyncMock, mock_ticker: MagicMock) -> None:
    """Test financials retrieval with no statement data."""
    mock_ticker_obj = MagicMock()
    mock_ticker_obj.income_stmt = pd.DataFrame()
    mock_ticker_obj.balance_sheet = pd.DataFrame()
    mock_ticker_obj.cashflow = pd.DataFrame()
    mock_ticker.return_value = mock_ticker_obj
    mock_to_thread.side_effect = _run_to_thread

    result = await get_financials("EMPTY", "annual")
    data = json.loads(result)

    assert data["error_code"] == "NO_DATA"
    assert data["details"] == {"symbol": "EMPTY", "frequency": "annual"}


@pytest.mark.asyncio
@pytest.mark.parametrize("exception", [TimeoutError("timed out"), OSError("network unreachable")])
@patch("yfmcp.server.yf.Ticker")
@patch("yfmcp.server.asyncio.to_thread")
async def test_get_financials_ticker_creation_network_error(
    mock_to_thread: AsyncMock, mock_ticker: MagicMock, exception: Exception
) -> None:
    """Test network errors while creating a ticker return structured network errors."""
    mock_ticker.side_effect = exception
    mock_to_thread.side_effect = _run_to_thread

    result = await get_financials("AAPL", "annual")
    data = json.loads(result)

    assert data["error_code"] == "NETWORK_ERROR"
    assert data["details"]["symbol"] == "AAPL"
    assert data["details"]["exception"] == str(exception)


@pytest.mark.asyncio
@patch("yfmcp.server.yf.Ticker")
@patch("yfmcp.server.asyncio.to_thread")
async def test_get_financials_statement_read_api_error(mock_to_thread: AsyncMock, mock_ticker: MagicMock) -> None:
    """Test statement read errors return structured API errors."""
    mock_ticker.return_value = _FinancialsReadErrorTicker()
    mock_to_thread.side_effect = _run_to_thread

    result = await get_financials("AAPL", "annual")
    data = json.loads(result)

    assert data["error_code"] == "API_ERROR"
    assert data["details"]["symbol"] == "AAPL"
    assert data["details"]["frequency"] == "annual"
    assert data["details"]["exception"] == "statement read failed"


@pytest.mark.asyncio
@patch("yfmcp.server.yf.Ticker")
@patch("yfmcp.server.asyncio.to_thread")
async def test_get_price_history_returns_markdown_table_when_chart_type_is_none(
    mock_to_thread: AsyncMock, mock_ticker: MagicMock
) -> None:
    """Test price history without chart_type returns DataFrame markdown output."""
    df = pd.DataFrame(
        {
            "Open": [100.0],
            "High": [110.0],
            "Low": [95.0],
            "Close": [105.0],
            "Volume": [1_000_000],
        },
        index=[pd.Timestamp("2024-01-02")],
    )
    mock_ticker_obj = MagicMock()
    mock_ticker_obj.history.return_value = df
    mock_ticker.return_value = mock_ticker_obj
    mock_to_thread.side_effect = _run_to_thread

    result = await get_price_history("AAPL", "1mo", "1d", None)

    assert isinstance(result, str)
    assert result == df.to_markdown()
    assert "Open" in result
    assert "Close" in result
    assert "|" in result


@pytest.mark.asyncio
@patch("yfmcp.server.yf.Sector")
@patch("yfmcp.server.asyncio.to_thread")
async def test_get_top_etfs_success(mock_to_thread: AsyncMock, mock_sector: MagicMock) -> None:
    """Test successful ETF retrieval."""
    # Mock the yfinance Sector object
    mock_sector_obj = MagicMock()
    mock_sector_obj.top_etfs = {"SPY": "SPDR S&P 500 ETF", "QQQ": "Invesco QQQ Trust"}

    # Setup asyncio.to_thread mock
    async def mock_thread_func(func, *args):
        if callable(func):
            return func(*args)
        return mock_sector_obj

    mock_to_thread.side_effect = mock_thread_func
    mock_sector.return_value = mock_sector_obj

    result = await get_top_etfs("Technology", 2)
    data = json.loads(result)

    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["symbol"] == "SPY"
    assert data[0]["name"] == "SPDR S&P 500 ETF"


@pytest.mark.asyncio
@patch("yfmcp.server.yf.Sector")
@patch("yfmcp.server.asyncio.to_thread")
async def test_get_top_etfs_no_data(mock_to_thread: AsyncMock, mock_sector: MagicMock) -> None:
    """Test ETF retrieval with no data."""
    mock_sector_obj = MagicMock()
    mock_sector_obj.top_etfs = {}

    async def mock_thread_func(func, *args):
        if callable(func):
            return func(*args)
        return mock_sector_obj

    mock_to_thread.side_effect = mock_thread_func
    mock_sector.return_value = mock_sector_obj

    result = await get_top_etfs("Technology", 2)
    data = json.loads(result)

    assert "error" in data
    assert data["error_code"] == "NO_DATA"
    assert "details" in data


@pytest.mark.asyncio
@patch("yfmcp.server.yf.Sector")
@patch("yfmcp.server.asyncio.to_thread")
async def test_get_top_etfs_api_error(mock_to_thread: AsyncMock, mock_sector: MagicMock) -> None:
    """Test ETF retrieval with API error."""
    mock_to_thread.side_effect = Exception("API Error")

    result = await get_top_etfs("Technology", 2)
    data = json.loads(result)

    assert "error" in data
    assert data["error_code"] == "API_ERROR"
    assert "details" in data
    assert "exception" in data["details"]


@pytest.mark.asyncio
@patch("yfmcp.server.yf.Sector")
@patch("yfmcp.server.asyncio.to_thread")
async def test_get_top_mutual_funds_success(mock_to_thread: AsyncMock, mock_sector: MagicMock) -> None:
    """Test successful mutual fund retrieval."""
    mock_sector_obj = MagicMock()
    mock_sector_obj.top_mutual_funds = {"FXAIX": "Fidelity 500 Index", "VTSAX": "Vanguard Total Stock"}

    async def mock_thread_func(func, *args):
        if callable(func):
            return func(*args)
        return mock_sector_obj

    mock_to_thread.side_effect = mock_thread_func
    mock_sector.return_value = mock_sector_obj

    result = await get_top_mutual_funds("Technology", 2)
    data = json.loads(result)

    assert isinstance(data, list)
    assert len(data) == 2


@pytest.mark.asyncio
@patch("yfmcp.server.yf.Sector")
@patch("yfmcp.server.asyncio.to_thread")
async def test_get_top_companies_success(mock_to_thread: AsyncMock, mock_sector: MagicMock) -> None:
    """Test successful company retrieval."""
    mock_sector_obj = MagicMock()
    mock_df = pd.DataFrame(
        {
            "symbol": ["AAPL", "MSFT", "GOOGL"],
            "name": ["Apple", "Microsoft", "Google"],
            "marketCap": [2000000000000, 1800000000000, 1500000000000],
        }
    )
    mock_sector_obj.top_companies = mock_df

    async def mock_thread_func(func, *args):
        if callable(func):
            return func(*args)
        return mock_sector_obj

    mock_to_thread.side_effect = mock_thread_func
    mock_sector.return_value = mock_sector_obj

    result = await get_top_companies("Technology", 3)
    data = json.loads(result)

    assert isinstance(data, list)
    assert len(data) == 3
    assert data[0]["symbol"] == "AAPL"


@pytest.mark.asyncio
@patch("yfmcp.server.yf.Sector")
@patch("yfmcp.server.asyncio.to_thread")
async def test_get_top_companies_empty_dataframe(mock_to_thread: AsyncMock, mock_sector: MagicMock) -> None:
    """Test company retrieval with empty dataframe."""
    mock_sector_obj = MagicMock()
    mock_sector_obj.top_companies = pd.DataFrame()

    async def mock_thread_func(func, *args):
        if callable(func):
            return func(*args)
        return mock_sector_obj

    mock_to_thread.side_effect = mock_thread_func
    mock_sector.return_value = mock_sector_obj

    result = await get_top_companies("Technology", 3)
    data = json.loads(result)

    assert "error" in data
    assert data["error_code"] == "NO_DATA"


@pytest.mark.asyncio
@patch("yfmcp.server.SECTOR_INDUSTY_MAPPING", {"Technology": ["Software", "Hardware"]})
@patch("yfmcp.server.yf.Industry")
@patch("yfmcp.server.asyncio.to_thread")
async def test_get_top_growth_companies_success(mock_to_thread: AsyncMock, mock_industry: MagicMock) -> None:
    """Test successful growth company retrieval."""
    mock_industry_obj = MagicMock()
    mock_df = pd.DataFrame(
        {
            "symbol": ["NVDA", "AMD"],
            "name": ["NVIDIA", "AMD"],
            "growth": [50.0, 45.0],
        }
    )
    mock_industry_obj.top_growth_companies = mock_df

    async def mock_thread_func(func, *args):
        if callable(func):
            return func(*args)
        return mock_industry_obj

    mock_to_thread.side_effect = mock_thread_func
    mock_industry.return_value = mock_industry_obj

    result = await get_top_growth_companies("Technology", 2)
    data = json.loads(result)

    assert isinstance(data, list)
    assert len(data) > 0
    assert "industry" in data[0]
    assert "top_growth_companies" in data[0]


@pytest.mark.asyncio
async def test_get_top_growth_companies_invalid_sector() -> None:
    """Test growth company retrieval with invalid sector."""
    result = await get_top_growth_companies("InvalidSector", 2)  # ty:ignore[invalid-argument-type]
    data = json.loads(result)

    assert "error" in data
    assert data["error_code"] == "INVALID_PARAMS"
    assert "valid_sectors" in data["details"]


@pytest.mark.asyncio
@patch("yfmcp.server.SECTOR_INDUSTY_MAPPING", {"Technology": ["Software"]})
@patch("yfmcp.server.yf.Industry")
@patch("yfmcp.server.asyncio.to_thread")
async def test_get_top_performing_companies_success(mock_to_thread: AsyncMock, mock_industry: MagicMock) -> None:
    """Test successful performing company retrieval."""
    mock_industry_obj = MagicMock()
    mock_df = pd.DataFrame(
        {
            "symbol": ["TSLA"],
            "name": ["Tesla"],
            "performance": [100.0],
        }
    )
    mock_industry_obj.top_performing_companies = mock_df

    async def mock_thread_func(func, *args):
        if callable(func):
            return func(*args)
        return mock_industry_obj

    mock_to_thread.side_effect = mock_thread_func
    mock_industry.return_value = mock_industry_obj

    result = await get_top_performing_companies("Technology", 1)
    data = json.loads(result)

    assert isinstance(data, list)
    assert len(data) > 0


@pytest.mark.asyncio
@patch("yfmcp.server.SECTOR_INDUSTY_MAPPING", {"Technology": []})
async def test_get_top_growth_companies_no_industries() -> None:
    """Test growth company retrieval with no industries."""
    result = await get_top_growth_companies("Technology", 2)
    data = json.loads(result)

    assert "error" in data
    assert data["error_code"] == "NO_DATA"
