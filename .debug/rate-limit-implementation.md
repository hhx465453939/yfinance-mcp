# Rate Limit & Cache Implementation

## 元信息

- 创建时间: 2026-04-26
- 分支: feat/rate-limit-and-cache
- 关联任务: market-alpha / deep-research 并行 info-collector 导致 Yahoo Finance 429

## 问题背景

多个 MCP agent 并行调用 yfmcp 时，Yahoo Finance 服务端返回 429 Too Many Requests。

根因:
1. 每次 tool call 都新建 `yf.Ticker()` 实例（无 session 复用）
2. yfinance 内部每次实例化都要获取 cookie + crumb（额外 2 次 HTTP）
3. 无请求间隔控制，3 个 info-collector 并发时瞬间 9+ 请求
4. 无本地缓存，相同查询重复请求

## 改动清单

### 新增: `src/yfmcp/throttle.py`

提供三层保护:

1. **asyncio throttle**（零依赖，始终生效）
   - 全局 asyncio.Lock + 最小请求间隔（默认 1.5s）
   - 保证串行请求，不会并发打到 Yahoo
   - 环境变量 `YFMCP_MIN_INTERVAL` 可调

2. **CachedLimiterSession**（可选，需额外依赖）
   - `requests-cache`: SQLite 缓存，相同请求 5 分钟内直接返回
   - `requests-ratelimiter`: HTTP 层面每 3 秒最多 1 次请求
   - session 复用：cookie + crumb 只获取一次
   - 优雅降级：依赖未安装时仅靠 asyncio throttle

3. **便捷包装函数**
   - `make_ticker(symbol)`: throttle + session + Ticker 一步到位
   - `throttled_download(**kwargs)`: throttle + session + download

环境变量:
- `YFMCP_MIN_INTERVAL`: 请求最小间隔秒数（默认 1.5）
- `YFMCP_CACHE_DIR`: 缓存目录（默认 /tmp/yfmcp-cache）
- `YFMCP_CACHE_EXPIRE`: 缓存 TTL 秒数（默认 300）

### 修改: `pyproject.toml`

新增依赖:
- `requests-cache>=1.0.0`
- `requests-ratelimiter>=0.4.0`
- `pyrate-limiter>=3.0.0`

### 修改: `src/yfmcp/server.py`

- import `make_ticker`, `throttle`
- 3 处 `yf.Ticker(symbol)` → `make_ticker(symbol)`
- 1 处 `yf.Search(query)` 前加 `await throttle()`
- 3 处 `yf.Sector(sector)` 前加 `await throttle()`
- 2 处 `yf.Industry(name)` 前加 `await throttle()`

### 修改: `src/yfmcp/extended.py`

- import `make_ticker`, `throttled_download`
- 8 处 `yf.Ticker(symbol)` → `make_ticker(symbol)`
- 1 处 `yf.download(**kwargs)` → `throttled_download(**kwargs)`

## 预期效果

- 并行 agent 调用 yfmcp 时不再触发 Yahoo 429
- 相同 symbol 的重复查询走本地缓存（5 分钟 TTL）
- cookie-crumb 只获取一次并复用
- 不安装额外依赖时仍有 asyncio throttle 兜底

## 风险与注意

- asyncio throttle 使所有 yfinance 调用串行化，单个请求延迟增加 ~1.5s
- 缓存 5 分钟 TTL，盘前/盘后切换期间数据可能不是最新
- `YFMCP_CACHE_DIR` 需要容器内有写权限
- 需要在容器内执行 `uv sync` 安装新依赖
