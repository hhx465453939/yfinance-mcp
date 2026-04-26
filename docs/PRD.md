# Yahoo Finance MCP（yfmcp）产品需求说明（PRD）

| 项目 | 说明 |
|------|------|
| 文档版本 | 0.2（2026-04-20 增补 §5 扩展工具，详见 §3.7） |
| 基线代码版本 | yfmcp 0.8.3（见 `pyproject.toml`） |
| 基线仓库路径 | `E:\Development\yfinance-mcp` |
| 上游数据依赖 | [yfinance](https://github.com/ranaroussi/yfinance)（PyPI：`yfinance>=1.2.0`） |
| 文档用途 | 记录**当前对外能力**与**部署形态**，作为后续改造 MCP 的需求基线 |

---

## 1. 产品定位

为 AI Agent（MCP 客户端）提供只读雅虎财经数据能力：标的摘要、新闻、搜索、板块内排行、历史行情（表格或图表）。**不**承诺覆盖 yfinance 全部 API。

---

## 2. 对外暴露能力总览（MCP Tools）

当前通过 `FastMCP` 注册、对 Agent **可见且可调用的 MCP 工具共 14 个**（名称即客户端 `tools/list` 中的 `name`）：

- §3.1～§3.5 的 5 个核心工具（既有）
- §3.7 的 9 个扩展工具（v0.2 新增，对应 §5 PRD 改造项）

---

## 3. MCP 工具完整清单（Function / Tool 列表）

以下按 **MCP 工具名** 列出，并给出 Python 实现函数、参数与返回值形态。

### 3.1 `yfinance_get_ticker_info`

| 项 | 内容 |
|----|------|
| **实现函数** | `yfmcp.server:get_ticker_info` |
| **底层 yfinance** | `yfinance.Ticker(symbol)` → `.info` |
| **参数** | `symbol: str`（必填）— 雅虎符号，如 `AAPL`、`600519.SS` |
| **成功返回** | JSON 字符串：`ticker.info` 字典（部分时间类数值会格式化为可读日期字符串） |
| **失败返回** | JSON 字符串：`{"error", "error_code", "details?}`（`NETWORK_ERROR` / `API_ERROR` / `INVALID_SYMBOL` 等） |
| **注解** | `readOnlyHint=True`，`idempotentHint=True`，`openWorldHint=True` |

### 3.2 `yfinance_get_ticker_news`

| 项 | 内容 |
|----|------|
| **实现函数** | `yfmcp.server:get_ticker_news` |
| **底层 yfinance** | `yfinance.Ticker(symbol)` → `.get_news()` |
| **参数** | `symbol: str`（必填） |
| **成功返回** | JSON 字符串：新闻列表（结构见 README） |
| **失败返回** | 结构化错误 JSON（`NO_DATA` / `NETWORK_ERROR` / `API_ERROR`） |
| **注解** | 同上 |

### 3.3 `yfinance_search`

| 项 | 内容 |
|----|------|
| **实现函数** | `yfmcp.server:search` |
| **底层 yfinance** | `yfinance.Search(query)` → `.all` / `.quotes` / `.news` |
| **参数** | `query: str`（必填）；`search_type: SearchType`（必填，见 §4.1） |
| **成功返回** | JSON 字符串：与 `search_type` 对应的对象或数组 |
| **失败返回** | 结构化错误 JSON（含 `INVALID_PARAMS`） |
| **注解** | 同上 |

### 3.4 `yfinance_get_top`

| 项 | 内容 |
|----|------|
| **实现函数** | `yfmcp.server:get_top`（内部路由到多个 helper） |
| **底层 yfinance** | `yfinance.Sector(sector)`：`top_etfs`、`top_mutual_funds`、`top_companies`；`yfinance.Industry(name)`：`top_growth_companies`、`top_performing_companies`；行业列表来自 `yfinance.const.SECTOR_INDUSTY_MAPPING` |
| **参数** | `sector: Sector`（必填）；`top_type: TopType`（必填）；`top_n: int`（可选，默认 `10`，范围 `1～100`） |
| **成功返回** | JSON 字符串：依 `top_type` 为 ETF/基金列表、`top_companies` 的 DataFrame 记录、或按行业分组的成长/表现公司列表 |
| **失败返回** | 结构化错误 JSON |
| **注解** | 同上 |

**内部实现函数（非独立 MCP 工具，仅供 `get_top` 调度）**

| Python 函数 | 用途 |
|-------------|------|
| `get_top_etfs` | 板块热门 ETF |
| `get_top_mutual_funds` | 板块热门共同基金 |
| `get_top_companies` | 板块市值头部公司 |
| `get_top_growth_companies` | 各子行业成长头部（多 `Industry` 循环） |
| `get_top_performing_companies` | 各子行业股价表现头部 |

### 3.5 `yfinance_get_price_history`

| 项 | 内容 |
|----|------|
| **实现函数** | `yfmcp.server:get_price_history` |
| **底层 yfinance** | `yfinance.Ticker(symbol)` → `.history(period=..., interval=..., rounding=True)` |
| **参数** | `symbol: str`（必填）；`period: Period`（可选，默认 `"1mo"`）；`interval: Interval`（可选，默认 `"1d"`）；`chart_type: ChartType \| null`（可选，默认 `null` 表示不要图） |
| **成功返回（无图）** | Markdown 表格字符串：`DataFrame.to_markdown()`（含 OHLCV、Dividends、Stock Splits 等列，以实际 DataFrame 为准） |
| **成功返回（有图）** | `mcp.types.ImageContent`：由 `yfmcp.chart.generate_chart` 生成 WebP 图 |
| **失败返回** | 结构化错误 JSON（含 `NO_DATA` 对空 DataFrame） |
| **注解** | 同上 |

**关联图表能力（非 MCP 工具名，属库内函数）**

| Python 函数 | 说明 |
|-------------|------|
| `yfmcp.chart.generate_chart` | 输入 `symbol`、`df`、`chart_type`，返回 `ImageContent` |

### 3.6 进程入口（CLI）

| 入口 | 说明 |
|------|------|
| `yfmcp`（console_script） | `pyproject.toml`：`yfmcp = "yfmcp.server:main"` → `FastMCP.run()`；启动时显式 `import yfmcp.extended` 触发 §3.7 工具注册 |
| 脚本 `scripts/generate_sample_chart.py` | 开发/示例用，**不是** MCP 工具 |
| 脚本 `.debug/smoke_tools_list.py` | 部署自检：通过 stdio 启动 `yfmcp` 并断言 `tools/list` 含全部 14 个工具 |

### 3.7 扩展 MCP 工具（v0.2 新增，覆盖 §5 改造项）

实现位于 `src/yfmcp/extended.py`，统一沿用既有 `ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)` 与 `create_error_response()` 错误协议。

| MCP 工具 | 实现函数 | 底层 yfinance | 关键参数 |
|----------|----------|----------------|----------|
| `yfinance_download` | `extended:download` | `yf.download(tickers=..., group_by="ticker")` | `symbols: list[str]`（1～50）、`period`/`interval`、`start?`/`end?`（YYYY-MM-DD）、`auto_adjust`、`prepost` |
| `yfinance_get_history_advanced` | `extended:get_history_advanced` | `Ticker.history(start=, end=, ...)` | `symbol`、`start?`/`end?`、`period`、`interval`、`auto_adjust`、`actions`、`prepost`、`repair`、`chart_type?` |
| `yfinance_get_financials` | `extended:get_financials` | `Ticker.financials` / `balance_sheet` / `cashflow`（含 `quarterly_*`） | `symbol`、`statement: income\|balance\|cashflow`、`quarterly: bool=False` |
| `yfinance_get_options` | `extended:get_options` | `Ticker.options` + `Ticker.option_chain(expiration)` | `symbol`；`expiration?`（None=只列到期日） |
| `yfinance_get_recommendations` | `extended:get_recommendations` | `Ticker.recommendations` | `symbol` |
| `yfinance_get_calendar` | `extended:get_calendar` | `Ticker.calendar` | `symbol` |
| `yfinance_get_holders` | `extended:get_holders` | `major_holders` / `institutional_holders` / `mutualfund_holders` | `symbol`、`holder_type: major\|institutional\|mutualfund`（默认 `institutional`） |
| `yfinance_get_insider_transactions` | `extended:get_insider_transactions` | `Ticker.insider_transactions` | `symbol` |
| `yfinance_get_fast_info` | `extended:get_fast_info` | `Ticker.fast_info` | `symbol` |

**返回约定**：

- 成功：JSON 字符串。表格类工具统一返回 `{"symbol": ..., "rows": [...]}` 或 `{"tickers": [...], "rows": [...]}`，列名经 `_df_to_records()` 强制转字符串以保证 JSON 可序列化。
- 失败：复用既有 `ErrorCode` 字面量（`INVALID_SYMBOL` / `NO_DATA` / `API_ERROR` / `INVALID_PARAMS` / `NETWORK_ERROR` / `UNKNOWN_ERROR`）。
- 图表：仅 `yfinance_get_history_advanced` 在传入 `chart_type` 时返回 `ImageContent`（其余均为 JSON 字符串）。

---

## 4. 类型与枚举（与实现对齐）

### 4.1 `SearchType`

`"all"` | `"quotes"` | `"news"`

### 4.2 `TopType`

`"top_etfs"` | `"top_mutual_funds"` | `"top_companies"` | `"top_growth_companies"` | `"top_performing_companies"`

### 4.3 `Sector`（与 `yfmcp.types` 一致）

`Basic Materials`、`Communication Services`、`Consumer Cyclical`、`Consumer Defensive`、`Energy`、`Financial Services`、`Healthcare`、`Industrials`、`Real Estate`、`Technology`、`Utilities`

### 4.4 `Period`

`1d`、`5d`、`1mo`、`3mo`、`6mo`、`1y`、`2y`、`5y`、`10y`、`ytd`、`max`

### 4.5 `Interval`

`1m`、`2m`、`5m`、`15m`、`30m`、`60m`、`90m`、`1h`、`1d`、`5d`、`1wk`、`1mo`、`3mo`

### 4.6 `ChartType`

`price_volume`、`vwap`、`volume_profile`

### 4.7 错误码 `ErrorCode`（JSON 内 `error_code`）

`INVALID_SYMBOL`、`NO_DATA`、`API_ERROR`、`INVALID_PARAMS`、`NETWORK_ERROR`、`UNKNOWN_ERROR`

---

## 5. yfinance 能力暴露状态

> v0.2 更新：以下五项「未暴露能力」中的前四项已通过 §3.7 工具补齐，第五项保留待评估。

| 项 | 状态 | 对应工具 |
|----|------|----------|
| `yf.download` / `yf.Tickers` 批量行情 | ✅ 已暴露 | `yfinance_download` |
| `Ticker.history` 的 `start`/`end`、`auto_adjust`、`actions`、`prepost`、`repair` 等参数 | ✅ 已暴露 | `yfinance_get_history_advanced`（既有 `yfinance_get_price_history` 保留向后兼容） |
| 财务报表 `financials` / `balance_sheet` / `cashflow`（含季度） | ✅ 已暴露 | `yfinance_get_financials`（参数 `statement` + `quarterly`） |
| 期权链 / 持有人 / 内部人交易 / `recommendations` / `calendar` / `fast_info` | ✅ 已暴露 | `yfinance_get_options` / `yfinance_get_holders` / `yfinance_get_insider_transactions` / `yfinance_get_recommendations` / `yfinance_get_calendar` / `yfinance_get_fast_info` |
| `screener` / `lookup` / `live` / `calendars` 等较新或独立模块 | 🚧 待评估 | 视上游 yfinance 版本稳定度按需纳入 v0.3 |

（具体以所选 yfinance 版本文档为准。）

---

## 6. 部署与安装：venv 还是 uv？

### 6.1 结论摘要

| 场景 | 建议 |
|------|------|
| **本仓库开发与改造（推荐）** | **venv+uv**：先建项目内虚拟环境，再用 uv 在该环境中安装/运行，避免 uv 在系统/用户级写入二进制软链与缓存路径（实测 v0.2 流程见 §6.4）。 |
| **最终用户「零本地克隆」跑 MCP** | **uvx**：`uvx yfmcp@latest`（README 推荐），由 uv 管理临时环境，无需手工 venv。 |
| **企业策略强制「项目内 venv」** | 使用 **venv + pip**：`python -m venv .venv` → `pip install -e .` 或 `pip install yfmcp`，MCP 配置里把 `command` 指向该 venv 的 `yfmcp` 可执行文件。 |
| **容器** | 保持 Docker 方案；镜像内用 pip 或 uv 均可，以镜像构建规范为准。 |

### 6.2 对比说明

- **uv**  
  - 优点：锁文件、与 `uv run`/`uvx` 集成、与本项目维护方式一致。  
  - 注意：需在环境上安装 [uv](https://docs.astral.sh/uv/)；MCP 配置中 `command` 为 `uv` 或 `uvx`。  

- **venv**  
  - 优点：仅标准库即可创建虚拟环境，运维认知成本低。  
  - 缺点：需自行固定 `pip install` 版本或使用 `requirements.txt`/`pip-tools` 才能接近 uv 的锁文件体验；与当前仓库以 uv 为主的工作流略分裂。  

### 6.3 MCP 客户端配置示例（改造后仍适用）

- **uvx（推荐终端用户）**：`command: uvx`，`args: ["yfmcp@latest"]`  
- **克隆仓库开发**：`command: uv`，`args: ["run", "--directory", "<repo>", "yfmcp"]`  
- **venv**：`command: "<repo>/.venv/Scripts/yfmcp.exe"`（Windows）或 `"<repo>/.venv/bin/yfmcp"`（Unix），`args: []`  

### 6.4 venv+uv 标准流程（v0.2 实测，Windows PowerShell）

```powershell
python -m venv .venv                       # 项目内虚拟环境，避免污染全局
.\.venv\Scripts\Activate.ps1               # 激活后 VIRTUAL_ENV 指向 .venv
uv sync --active                           # 在已激活 venv 中解析 + 安装依赖
uv run --active ruff check .               # Lint
uv run --active ruff format --check .      # Format
uv run --active ty check src tests         # Type
uv run --active pytest -v --cov=src tests  # Test
yfmcp                                      # 启动 MCP server（stdio）
python .debug\smoke_tools_list.py          # 部署自检：tools/list 应输出 14 项
```

Linux / macOS 同义命令：把 `\.venv\Scripts\Activate.ps1` 换成 `source .venv/bin/activate`，路径分隔符改 `/`。

---

## 7. 改造范围建议（占位）

后续版本可在本文档上增量维护：

1. **工具拆分/合并**：例如将 `get_top` 拆为多个 MCP 工具以降低单轮参数歧义。  
2. **暴露度**：按业务优先级增加 `history` 完整参数、财报、批量下载等工具。  
3. **观测性**：统一错误码、日志字段、可选 request_id。  
4. **安全与配额**：雅虎限流说明、客户端重试策略、缓存策略。  

---

## 8. 文档与代码索引

| 资源 | 路径 |
|------|------|
| MCP 核心实现（5 工具） | `src/yfmcp/server.py` |
| MCP 扩展实现（9 工具，v0.2 新增） | `src/yfmcp/extended.py` |
| 图表 | `src/yfmcp/chart.py` |
| 类型字面量 | `src/yfmcp/types.py` |
| JSON / 错误工具 | `src/yfmcp/utils.py` |
| 单元测试（核心 + 扩展，全部 mock） | `tests/test_server_unit.py`、`tests/test_extended.py`、`tests/test_chart.py`、`tests/test_types.py` |
| 真实网络集成测试（按需） | `tests/test_server.py` |
| 部署自检脚本 | `.debug/smoke_tools_list.py` |
| Debug 记录 | `.debug/feature-exposure.md` |
| 用户说明 | `README.md` |

---

*本文档由基线代码与 README 整理生成，用于 MCP 改造前的需求冻结与评审。*
