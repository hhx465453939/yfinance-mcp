# Yahoo Finance MCP 服务器

[![PyPI version](https://img.shields.io/pypi/v/yfmcp)](https://pypi.org/project/yfmcp/)
[![Python](https://img.shields.io/pypi/pyversions/yfmcp.svg)](https://pypi.org/project/yfmcp/)
[![CI](https://github.com/narumiruna/yfinance-mcp/actions/workflows/python.yml/badge.svg)](https://github.com/narumiruna/yfinance-mcp/actions/workflows/python.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

一个 [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) 服务器，通过 [yfinance](https://github.com/ranaroussi/yfinance) 把 Yahoo Finance 的数据接入到 AI 助手里。可在 Cursor / Claude Desktop / Cline 等任意 MCP 客户端中查询股票信息、公司新闻、板块排行，并直接生成专业行情图表。

<a href="https://glama.ai/mcp/servers/@narumiruna/yfinance-mcp">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/@narumiruna/yfinance-mcp/badge" />
</a>

## 功能特性

- **股票数据** — 公司信息、财务、估值指标、分红与交易数据
- **公司新闻** — 任意标的的最新新闻与公告
- **搜索** — 在 Yahoo Finance 中检索股票、ETF 与新闻
- **板块排行** — 板块内热门 ETF / 共同基金 / 头部公司 / 成长龙头 / 价格表现领先股
- **历史行情** — Markdown 表格或专业图表两种返回形态
- **图表生成** — K 线、VWAP、成交量分布图，统一以 WebP 图像返回，token 友好

---

## 工具清单（共 14 个）

### 核心工具（5 个）

#### `yfinance_get_ticker_info`

获取单只股票的综合数据：公司资料、财务、交易指标、治理信息等。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `symbol` | string | 是 | 股票代码（如 `AAPL`、`GOOGL`、`MSFT`、`600519.SS`） |

**返回**：JSON 对象，包含公司详情、价格数据、估值、交易、分红、财务和绩效指标。

#### `yfinance_get_ticker_news`

抓取某只股票的最新新闻与公告。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `symbol` | string | 是 | 股票代码 |

**返回**：JSON 数组，包含标题、摘要、发布时间、来源、链接、缩略图等。

#### `yfinance_search`

在 Yahoo Finance 中搜索股票、ETF 和新闻。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | string | 是 | 搜索关键词（公司名、代码或关键字） |
| `search_type` | string | 是 | `"all"`（行情 + 新闻）/ `"quotes"`（仅证券）/ `"news"`（仅新闻） |

**返回**：根据 `search_type` 返回对应结构。

#### `yfinance_get_top`

按板块获取头部金融实体的排行。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `sector` | string | 是 | 板块名（见 [支持的板块](#支持的板块)） |
| `top_type` | string | 是 | `"top_etfs"` / `"top_mutual_funds"` / `"top_companies"` / `"top_growth_companies"` / `"top_performing_companies"` |
| `top_n` | number | 否 | 返回条数（默认 `10`，最大 `100`） |

**返回**：JSON 数组。

##### 支持的板块

`Basic Materials`、`Communication Services`、`Consumer Cyclical`、`Consumer Defensive`、`Energy`、`Financial Services`、`Healthcare`、`Industrials`、`Real Estate`、`Technology`、`Utilities`

#### `yfinance_get_price_history`

获取历史行情数据，可选生成技术分析图表。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `symbol` | string | 是 | 股票代码 |
| `period` | string | 否 | 时间范围 — `1d`、`5d`、`1mo`、`3mo`、`6mo`、`1y`、`2y`、`5y`、`10y`、`ytd`、`max`（默认 `1mo`） |
| `interval` | string | 否 | 数据粒度 — `1m`、`2m`、`5m`、`15m`、`30m`、`60m`、`90m`、`1h`、`1d`、`5d`、`1wk`、`1mo`、`3mo`（默认 `1d`） |
| `chart_type` | string | 否 | 生成图表类型；省略则返回表格 |

**支持的图表类型**：

| 取值 | 说明 |
|------|------|
| `"price_volume"` | K 线 + 成交量柱状图 |
| `"vwap"` | 价格 + 成交量加权均价（VWAP）叠加 |
| `"volume_profile"` | K 线 + 价位分布的成交量条 |

**返回**：
- 不传 `chart_type`：Markdown 表格（Date、Open、High、Low、Close、Volume、Dividends、Stock Splits）。
- 传 `chart_type`：Base64 编码的 WebP 图像，节省 token。

### 扩展工具（v0.2 新增，9 个）

下列 9 个工具覆盖了 PRD §5 列出的"未暴露 yfinance 能力"。返回均为 JSON 字符串，错误协议复用核心工具的 `error` / `error_code` / `details` 结构。

| 工具 | 底层调用 | 关键参数 |
|------|----------|----------|
| `yfinance_download` | `yf.download(tickers=..., group_by="ticker")` | `symbols: string[]`（1–50）、`period`、`interval`、`start?`、`end?`（YYYY-MM-DD）、`auto_adjust=true`、`prepost=false` |
| `yfinance_get_history_advanced` | `Ticker.history(start=, end=, ...)` | `symbol`、`start?`、`end?`、`period`、`interval`、`auto_adjust`、`actions`、`prepost`、`repair`、`chart_type?` |
| `yfinance_get_financials` | `Ticker.financials` / `balance_sheet` / `cashflow`（含 `quarterly_*`） | `symbol`、`statement: "income" \| "balance" \| "cashflow"`、`quarterly: bool=false` |
| `yfinance_get_options` | `Ticker.options` + `Ticker.option_chain(date)` | `symbol`、`expiration?`（不填则只返回可选到期日列表） |
| `yfinance_get_recommendations` | `Ticker.recommendations` | `symbol` |
| `yfinance_get_calendar` | `Ticker.calendar` | `symbol` |
| `yfinance_get_holders` | `major_holders` / `institutional_holders` / `mutualfund_holders` | `symbol`、`holder_type: "major" \| "institutional" \| "mutualfund"`（默认 `institutional`） |
| `yfinance_get_insider_transactions` | `Ticker.insider_transactions` | `symbol` |
| `yfinance_get_fast_info` | `Ticker.fast_info` | `symbol` |

表格类工具统一返回 `{ "symbol": ..., "rows": [ {col: value, ...}, ... ] }`；`yfinance_download` 返回 `{ "tickers": [...], "rows": [ { "Ticker": ..., "Date": ..., ... }, ... ] }`。所有列名（包括 pandas 的 Timestamp）都会强制转换为字符串以保证 JSON 可序列化。

---

## 在 Cursor 中挂载（本地 venv 方案，推荐）

> 这是按本仓库已采用的 **venv + uv** 流程对应的客户端配置；优点是 Cursor 直接 spawn `.venv` 内的可执行文件，启动最快、依赖最确定，且和系统 Python 完全隔离。

### 1. 准备本地环境（仅首次）

```powershell
# Windows / PowerShell
git clone https://github.com/narumiruna/yfinance-mcp.git
cd yfinance-mcp
python -m venv .venv
.\.venv\Scripts\Activate.ps1
uv sync --active
```

```bash
# Linux / macOS
git clone https://github.com/narumiruna/yfinance-mcp.git
cd yfinance-mcp
python -m venv .venv
source .venv/bin/activate
uv sync --active
```

完成后，`.venv` 内会出现一个可直接启动 MCP 服务器的可执行文件：

- **Windows**：`<repo>\.venv\Scripts\yfmcp.exe`
- **Linux / macOS**：`<repo>/.venv/bin/yfmcp`

### 2. 写入 Cursor 的 MCP 配置

Cursor 的 MCP 配置位于：

| 作用范围 | 路径 |
|----------|------|
| **全局**（所有项目） | `%USERPROFILE%\.cursor\mcp.json`（Windows） / `~/.cursor/mcp.json`（macOS / Linux） |
| **项目级**（仅当前项目） | `<项目根>/.cursor/mcp.json`（与 Cursor 同打开的工作区） |

任选其一新建（或追加到既有 `mcpServers` 段）。**强烈建议用绝对路径**指向 venv 内的可执行文件——这样不管 Cursor 启动时的当前目录是什么，都能稳定拉起。

#### Windows 示例

```json
{
  "mcpServers": {
    "yfmcp": {
      "command": "E:\\Development\\yfinance-mcp\\.venv\\Scripts\\yfmcp.exe",
      "args": []
    }
  }
}
```

> 注意：JSON 里 Windows 路径要么用双反斜杠 `\\`，要么用正斜杠 `/`（如 `E:/Development/yfinance-mcp/.venv/Scripts/yfmcp.exe`）。

#### macOS / Linux 示例

```json
{
  "mcpServers": {
    "yfmcp": {
      "command": "/absolute/path/to/yfinance-mcp/.venv/bin/yfmcp",
      "args": []
    }
  }
}
```

### 3. 在 Cursor 里启用

1. 重启 Cursor（或在 Settings 里 Reload MCP Servers）。
2. 打开 **Settings → MCP**（或 `Cmd/Ctrl + ,` 搜索 `mcp`），看到 `yfmcp` 已列出且为绿色"connected"状态即生效。
3. 在 Agent 对话里直接说"帮我看下 AAPL 最新股价"或"用 yfinance 取 NVDA 季度财报"，模型会自动调用对应工具。

### 4. 自检（可选，但强烈建议）

```powershell
.\.venv\Scripts\Activate.ps1
python .\.debug\smoke_tools_list.py
```

预期最后一行：`PASS: tools/list matches expected set`，并列出全部 14 个工具。如果这里能跑通，Cursor 那边就一定能拉起来。

---

## 其他挂载方式

下列方式适用于不想克隆仓库、或想跑容器版的场景，配置同样可以写到 Cursor 的 `mcp.json`。

### 通过 uvx（无需克隆，最简单）

1. [安装 uv](https://docs.astral.sh/uv/getting-started/installation/)
2. 写入 MCP 配置：

```json
{
  "mcpServers": {
    "yfmcp": {
      "command": "uvx",
      "args": ["yfmcp@latest"]
    }
  }
}
```

> 首次启动会拉取并缓存包，稍慢；以后由 uv 在临时环境里运行。

### 通过 `uv run --directory`（克隆但不预先建 venv）

```json
{
  "mcpServers": {
    "yfmcp": {
      "command": "uv",
      "args": ["run", "--directory", "E:/Development/yfinance-mcp", "yfmcp"]
    }
  }
}
```

把 `E:/Development/yfinance-mcp` 替换成你实际的仓库路径。

### 通过 Docker

```json
{
  "mcpServers": {
    "yfmcp": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "narumi/yfinance-mcp"]
    }
  }
}
```

---

## 限流与缓存

yfinance-mcp 内置了请求限流和可选的结果缓存，避免多 agent 并发调用时触发 Yahoo Finance 的 429 限速。

### 限流（默认开启）

所有 yfinance 请求经过 asyncio 全局锁串行化，最小间隔 1.5 秒。无额外依赖，开箱即用。

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `YFMCP_MIN_INTERVAL` | `1.5` | 连续请求最小间隔（秒） |

### 结果缓存（可选）

在 MCP tool 返回值层面缓存 JSON 结果，相同参数 + TTL 内直接返回缓存，不再请求 Yahoo。与 yfinance 内部的 curl_cffi 完全兼容。

在 MCP 客户端配置的 `env` 中设置 `YFMCP_RESULT_CACHE_DIR` 即可启用，不设置则不缓存。

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `YFMCP_RESULT_CACHE_DIR` | （空） | 缓存目录路径。设置后启用缓存，不设置则禁用 |
| `YFMCP_RESULT_CACHE_TTL` | `300` | 缓存有效期（秒） |

配置示例（Docker / mcporter）：

```json
{
  "yfmcp": {
    "command": "...",
    "env": {
      "YFMCP_RESULT_CACHE_DIR": "/home/node/.openclaw/.cache/yfmcp-results",
      "YFMCP_RESULT_CACHE_TTL": "300"
    }
  }
}
```

---

## 常见问题（Cursor 挂载排查）

| 现象 | 排查方向 |
|------|---------|
| Cursor 里 `yfmcp` 一直 loading 或红点 | 1) 在系统终端里手动跑 `command + args` 是否能起来；2) 检查 `command` 是否绝对路径；3) 看 Cursor 的 Output → MCP 日志 |
| 报 `command not found: yfmcp` | 没有指向 `.venv` 内的可执行文件，把 `command` 改成 `<repo>/.venv/Scripts/yfmcp.exe` 或 `<repo>/.venv/bin/yfmcp` 的绝对路径 |
| 报 `ImportError: tabulate` | 你的本地依赖落后，重新跑 `uv sync --active`；最新版已把 `tabulate>=0.9.0` 列入运行时依赖 |
| 路径中含中文 / 空格启动失败 | 把 JSON 里的路径整段用双引号包裹（已是字符串值无需额外转义），并优先用正斜杠 `/` |
| Windows 上想用 PowerShell 别名 / conda env | 不要把 `command` 设成 `powershell` 或 `conda` 再嵌套调用——直接指向 venv 里的 `yfmcp.exe` 最稳 |

---

## 开发

### 前置依赖

- Python ≥ 3.12
- [uv](https://docs.astral.sh/uv/) 包管理器

### 初始化（推荐 venv + uv）

先在项目根创建虚拟环境，再让 `uv` 在该环境内执行所有操作。这样 `uv` 不会往用户级 / 系统级 Python 路径或缓存里写东西。

PowerShell（Windows）：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
uv sync --active
```

bash / zsh（Linux / macOS）：

```bash
python -m venv .venv
source .venv/bin/activate
uv sync --active
```

如果你不在意环境隔离，单独 `uv sync` 也行（它会自动建 `.venv`）；`venv + uv sync --active` 只是更显式，对要审计 PATH / 缓存变化的团队更友好。

### Lint & Format

```bash
uv run --active ruff check .
uv run --active ruff format .
```

### 类型检查

```bash
uv run --active ty check src tests
```

### 测试

```bash
uv run --active pytest -v -s --cov=src tests
```

### 部署自检

`uv sync --active` 之后，端到端验证全部 14 个 MCP 工具都已注册：

```bash
python .debug/smoke_tools_list.py
```

预期输出末行：`PASS: tools/list matches expected set`。

---

## Demo Chatbot

参考独立仓库：[yfinance-mcp-demo](https://github.com/narumiruna/yfinance-mcp-demo)

## Contributors

<a href="https://github.com/narumiruna/yfinance-mcp/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=narumiruna/yfinance-mcp" />
</a>

Made with [contrib.rocks](https://contrib.rocks).

## License

本项目使用 [MIT License](LICENSE) 协议。
