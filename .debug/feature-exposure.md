# Debug 记录 — 功能暴露扩展（PRD §5）

## 模块归属

`src/yfmcp/extended.py`（新增）+ `tests/test_extended.py`（新增）。
独立模块，不修改既有 5 个 MCP 工具的行为，仅追加注册。

## 运行上下文 / 测试规则（首次确认，后续优先复用）

| 项 | 值 |
|----|----|
| 部署形态 | 本机 Windows / PowerShell |
| Python | `python -m venv .venv`（项目内）→ Python 3.13.5 |
| 包管理 | **venv + uv**（在 .venv 激活后用 `uv sync --active`，避免 uv 在系统 / 用户级环境写入路径） |
| 启动 | `.\.venv\Scripts\Activate.ps1; yfmcp` |
| Lint/Type/Test | `uv run --active ruff check .` / `uv run --active ty check src tests` / `uv run --active pytest -v -s --cov=src tests` |
| 测试隔离 | 所有新工具单测使用 `unittest.mock.patch` mock `yf.Ticker`/`yf.download`/`asyncio.to_thread`，**不发起真实网络请求**；与既有 `tests/test_server.py::test_get_ticker_info`（真实网络）保持分离 |

## 上下文关系网络

### 调用链

```
mcp.run()
  └── yfmcp.server:main()
        ├── (隐式) 已注册 5 个 @mcp.tool（既有）
        └── from yfmcp import extended  # 触发 extended.py 模块级 @mcp.tool 装饰器执行
              └── 注册 9 个新工具到同一个 mcp 实例
```

### 关键变量依赖

- `mcp = FastMCP("yfinance_mcp", ...)` 在 `server.py` 顶层创建；`extended.py` 通过 `from yfmcp.server import mcp` 共享同一实例。
- 所有阻塞 yfinance 调用必须经 `asyncio.to_thread()`（与既有约定一致，AGENTS.md）。
- 错误统一走 `create_error_response()` 返回结构化 JSON（`error` / `error_code` / `details`）。
- 图表只在 `yfinance_get_price_history` 中产出 `ImageContent`；新工具均返回 JSON 字符串。

## 新增 MCP 工具清单

| 工具名 | 实现函数 | 底层 yfinance | 主要参数 |
|--------|----------|----------------|----------|
| `yfinance_download` | `extended.download` | `yf.download(tickers=...)` | `symbols: list[str]`, `period`, `interval`, `start?`, `end?`, `auto_adjust=True` |
| `yfinance_get_history_advanced` | `extended.get_history_advanced` | `Ticker.history(start=, end=, ...)` | `symbol`, `start?`, `end?`, `interval`, `auto_adjust`, `actions`, `prepost`, `repair`, `chart_type?` |
| `yfinance_get_financials` | `extended.get_financials` | `Ticker.financials` / `balance_sheet` / `cashflow`（含 `quarterly_*`） | `symbol`, `statement: income/balance/cashflow`, `quarterly: bool=False` |
| `yfinance_get_options` | `extended.get_options` | `Ticker.options` + `Ticker.option_chain(date)` | `symbol`, `expiration?`（None=只返到期日列表） |
| `yfinance_get_recommendations` | `extended.get_recommendations` | `Ticker.recommendations` | `symbol` |
| `yfinance_get_calendar` | `extended.get_calendar` | `Ticker.calendar` | `symbol` |
| `yfinance_get_holders` | `extended.get_holders` | `major_holders` / `institutional_holders` / `mutualfund_holders` | `symbol`, `holder_type` |
| `yfinance_get_insider_transactions` | `extended.get_insider_transactions` | `Ticker.insider_transactions` | `symbol` |
| `yfinance_get_fast_info` | `extended.get_fast_info` | `Ticker.fast_info` | `symbol` |

## 设计决策

1. **独立模块**：避免 `server.py` 膨胀到 1500+ 行，保持 PRD §3.1～3.5 的 5 个原工具区块清晰。
2. **延迟注册**：`server.py:main()` 中再导入 `extended`，防止 `from yfmcp.server import mcp` 与模块顶层 `@mcp.tool` 之间的初始化时序问题；同时 pytest 通过显式 `import yfmcp.extended` 触发注册。
3. **错误码复用**：沿用现有 `ErrorCode` Literal，不新增类型，降低客户端适配成本。
4. **`start`/`end` 参数解析**：接受 ISO `YYYY-MM-DD` 字符串；非法格式落入 `INVALID_PARAMS`。
5. **`yf.download` 多 symbol 返回**：列模式可能是 `MultiIndex`，统一用 `.to_dict()` 序列化时通过 `df.reset_index().to_dict(orient="records")` 拍平，并在 `details` 中带回 `tickers`。

## Checkfix 结果（最终轮）

| 步骤 | 命令 | 结果 |
|------|------|------|
| 环境 | `python -m venv .venv` + `.\.venv\Scripts\Activate.ps1` + `uv sync --active` | OK，76 个包安装到 `.venv`（含新增 `tabulate==0.10.0`），`yfmcp` 入口可用 |
| Lint | `uv run --active ruff check .` | `All checks passed!` |
| Format | `uv run --active ruff format --check .` | `13 files already formatted` |
| Type | `uv run --active ty check src tests` | `All checks passed!` |
| Test | `uv run --active pytest -v tests/test_extended.py tests/test_server_unit.py tests/test_chart.py tests/test_types.py` | **46 passed in 5.66s** |
| 部署自检 | `python .debug\smoke_tools_list.py` | **PASS: tools/list matches expected set** — 14 个工具齐全（5 既有 + 9 新增） |

## 中轮发现并修复的问题

| # | 现象 | 根因 | 修复 |
|---|------|------|------|
| 1 | `download` 函数复杂度 13>10（Ruff C901） | 行内同时处理 kwargs 装配 + MultiIndex 拍平 | 抽出 `_build_download_kwargs` 与 `_flatten_download_frame` 两个 helper |
| 2 | `to_markdown()` 抛 `ImportError: tabulate` | 既有项目 `pyproject.toml` 漏掉 pandas `to_markdown` 的可选依赖 `tabulate` | 在 `[project].dependencies` 增加 `tabulate>=0.9.0`（既有 `yfinance_get_price_history` 也受益） |
| 3 | `dump_json(financials)` 抛 `TypeError: keys must be str/...` | 财报 DataFrame 的列是 `pd.Timestamp`，原生 `json` 不接受 Timestamp 作 dict key | 在 `_df_to_records` 中对非 MultiIndex 列也强制 `[str(c) for c in df.columns]` |
| 4 | `ty` 报 `unused-type-ignore-comment` | 误用 mypy 风格 `# type: ignore`，且 ty 实际不报这两处 | 直接移除多余的 ignore 注释 |
| 5 | smoke 脚本顶部 docstring `\.venv` 触发 SyntaxWarning | 普通字符串里的 `\.` | 改为 raw docstring `r"""..."""` |

## 回滚

- 删除 `src/yfmcp/extended.py`、`tests/test_extended.py`，回滚 `src/yfmcp/server.py:main()` 中的 `import yfmcp.extended`；
- 已更新的 `README.md` / `PRD.md` 段落保持文档独立可恢复。
