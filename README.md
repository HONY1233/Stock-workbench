# AKShare MCP Server

基于 [AKShare](https://github.com/akfamily/akshare) + [AxData](https://github.com/electkismet/AxData) 的金融数据 MCP 服务器，整合两个数据源，提供 A股、指数、ETF、期货、外围新闻、外围指数、涨跌停、龙虎榜、期权、新闻等金融数据查询，并支持英文内容自动翻译为中文。

## 功能特性

- **43 个 MCP 工具**，覆盖 A股/指数/ETF/期货/期权/外围新闻/外围指数等全品类金融数据
- **双数据源整合**：akshare + axdata，自动路由到最佳来源
- **统一数据查询接口** `data_query`：39 个统一别名，一个入口查询所有数据
- **多源 fallback**：东方财富 push2 不可用时自动 fallback 到新浪
- **自动参数转换**：新浪/TDX 代码格式互转，参数名映射
- **英文自动翻译**：内置 250+ 金融术语词典，离线将外围新闻/财经日历中的英文自动翻译为中文
- **三种部署模式**：stdio（IDE集成）、SSE、streamable-http

## 数据源

| 数据源 | 覆盖范围 |
|--------|----------|
| **新浪财经** | A股日线/实时、指数、ETF、期货、美股/港股指数、龙虎榜、期权 |
| **东方财富** | 涨停池/跌停池、板块行情、大盘指数、ETF 实时、全球期货、全球新闻 |
| **财联社** | 电报快讯、市场情绪、涨停池、板块热度、今日风口、今日主线 |
| **开盘红** | 市场情绪（真实涨停、ST涨跌） |
| **巨潮信息网** | 公告、公司概况、财务摘要、分红配送 |
| **腾讯财经** | A股历史日线 |
| **华尔街见闻** | 全球宏观财经日历（事件/重要性/今值/预期/前值） |
| **同花顺** | 全球财经新闻 |
| **上海期货交易所** | 期货市场要闻 |

## 英文翻译功能

内置金融术语词典（约 250 词条），覆盖：

- **央行/机构**：Federal Reserve→美联储, ECB→欧洲央行, FOMC→联邦公开市场委员会, BOJ→日本央行...
- **宏观经济指标**：CPI→消费者物价指数, GDP→国内生产总值, nonfarm payrolls→非农就业人数, unemployment rate→失业率...
- **市场术语**：bull market→牛市, bear market→熊市, rally→上涨, selloff→抛售, VIX→波动率指数...
- **货币/外汇**：dollar→美元, euro→欧元, yen→日元, pound→英镑, yuan→人民币...
- **指数**：Dow Jones→道琼斯, Nasdaq→纳斯达克, S&P 500→标普500, Hang Seng→恒生指数, Nikkei→日经指数...
- **商品**：crude oil→原油, Brent→布伦特原油, WTI→西德克萨斯中质原油, gold→黄金...
- **数据描述**：YoY→同比, MoM→环比, hawkish→鹰派, dovish→鸽派, rate cut→降息, rate hike→加息...

翻译策略：词典最长匹配 + 大小写不敏感，未匹配的英文原样保留。所有外围新闻工具默认开启翻译（`translate=True`）。

## 工具列表（62 个）

### 统一接口（2 个）
- `data_query` - 统一数据查询接口，支持 39 个别名，含英文翻译
- `data_interfaces` - 列出所有可用接口

### A股行情（4 个）
- `stock_zh_a_daily` - A股个股日线历史（前复权）
- `stock_zh_index_daily` - A股指数日线历史
- `stock_zh_index_spot` - A股指数实时行情
- `stock_zh_a_spot` - A股个股实时行情

### 财经新闻（4 个）
- `cls_telegraph` - 财联社电报（支持关键词/级别/标红/时间过滤）
- `news_cctv` - 新闻联播文字稿
- `news_economic_calendar` - 财经日历
- `stock_news` - 个股新闻

### 外围新闻（含英文翻译，11 个）
- `global_news_em` - 全球财经新闻（东方财富，自动翻译英文）
- `global_news_sina` - 全球财经快讯（新浪，自动翻译英文）
- `global_news_ths` - 全球财经新闻（同花顺，自动翻译英文）
- `wallstreet_news` - 华尔街见闻财经日历（自动翻译英文事件名）
- `futures_news_shmet` - 上海期货交易所新闻（自动翻译英文）
- `stock_us_news` - 美股个股新闻（自动翻译英文标题/内容）
- `translate_text` - 翻译英文文本为中文（金融术语词典，离线可用）
- `reuters_news` - 路透社(Reuters)相关财经新闻（含英文翻译，网络允许时直接抓取 RSS）
- `bloomberg_news` - 彭博社(Bloomberg)相关财经新闻（含英文翻译，网络允许时直接抓取 RSS）
- `bloomberg_billionaires` - 彭博亿万富豪榜（网络允许时可用）
- `global_news_search` - 全球财经新闻搜索（支持 Reuters/Bloomberg/关键词筛选）

### 巨潮信息（4 个）
- `stock_notice_cninfo` - 上市公司公告
- `stock_profile_cninfo` - 公司基本资料
- `stock_financial_abstract_cninfo` - 财务摘要
- `stock_dividend_cninfo` - 分红配送

### 期货（3 个）
- `futures_realtime` - 期货实时行情
- `futures_daily` - 期货历史日线
- `futures_global_spot` - 全球期货实时行情

### 外围指数（3 个）
- `index_us_daily` - 美股指数日线（道琼斯/纳斯达克/标普500）
- `index_hk_daily` - 港股指数日线（恒生/国企/恒生科技）
- `index_global_list` - 全球指数代码表

### ETF（2 个）
- `fund_etf_spot` - ETF 实时行情列表
- `fund_etf_daily` - ETF 历史日线

### AxData 专用工具（14 个）
- `stock_limit_up_pool` - 涨停池（含涨停原因、连板数、主力资金）
- `stock_limit_down_pool` - 跌停池
- `sector_realtime` - 板块实时行情
- `market_emotion_cls` - 财联社市场情绪
- `market_emotion_kph` - 开盘红市场情绪
- `cls_limit_up_pool` - 财联社涨停池
- `cls_sector_heat` - 财联社板块热度
- `cls_market_wind` - 财联社今日风口
- `cls_market_mainline` - 财联社今日主线
- `stock_lhb_daily` - 龙虎榜每日详情
- `stock_lhb_institution` - 龙虎榜机构席位
- `futures_main_display` - 期货主力合约展示
- `option_commodity_list` - 商品期权品种
- `option_cffex_hs300_list` - 沪深300期权合约

### a-stock-data 补充信息源（15 个）

> 提取自 [a-stock-data](https://github.com/simonlin1212/a-stock-data) 项目，覆盖行情、研报、信号、资金面、打板、期权、舆情 7 层

#### 行情/资金面
- `tencent_realtime_quote` - 腾讯财经实时行情（PE_TTM/PB/市值/换手率/涨跌停价，不封IP）
- `northbound_flow` - 北向资金(沪深港通)持股明细
- `stock_fund_flow` - 个股资金流向（主力/大单/中单/小单净流入）

#### 融资/大宗/筹码
- `margin_trading` - 融资融券数据（沪市/深市）
- `block_trade` - 大宗交易数据
- `holder_count` - 股东户数变化（筹码集中度）
- `lockup_release` - 限售解禁日历

#### 研报/预期
- `research_report` - 研报盈利预测（同花顺）
- `eps_forecast` - 一致预期EPS（同花顺）

#### 打板情绪
- `limit_up_broken` - 炸板池（曾涨停又开板）
- `limit_up_previous` - 昨日涨停池（今日表现）
- `limit_up_strong` - 强势股池（连板等）

#### 期权/舆情
- `option_t_quote` - ETF期权实时行情
- `hot_rank` - 东财人气排行榜
- `concept_belong` - 概念板块归属

## 安装

```bash
pip install -r requirements.txt
```

依赖：
- `akshare>=1.18.0` - 金融数据
- `fastmcp>=3.0.0` - MCP 框架
- `pandas>=2.0.0` - 数据处理
- `curl_cffi>=0.7.0` - HTTP 客户端
- `axdata>=0.1.0` - AxData 数据源

## 运行

### 方式一：启动脚本

```bash
cd akshare-mcp
./run.sh                # stdio 模式（默认，IDE集成）
./run.sh sse            # SSE 模式，0.0.0.0:8000
./run.sh sse 9000       # SSE 模式，端口 9000
./run.sh http 8080      # streamable-http 模式
./run.sh list           # 列出所有可用工具
```

### 方式二：直接运行

```bash
python3 server.py                          # stdio 模式
python3 server.py -t sse                   # SSE 模式
python3 server.py -t sse --port 9000       # SSE 模式，自定义端口
python3 server.py -t streamable-http       # HTTP 模式
python3 server.py --list                  # 列出工具
```

## MCP 配置

### Trae IDE / Claude Desktop / Cursor

在 MCP 配置文件中添加：

```json
{
  "mcpServers": {
    "akshare": {
      "command": "python3",
      "args": ["/path/to/akshare-mcp/server.py"],
      "env": {}
    }
  }
}
```

### SSE 远程连接

服务端启动：
```bash
./run.sh sse 8000
```

客户端配置：
```json
{
  "mcpServers": {
    "akshare": {
      "url": "http://localhost:8000/sse"
    }
  }
}
```

## 使用示例

### 统一查询接口

```python
# 查询个股日线（支持多种代码格式）
data_query(interface="stock_daily", params_json='{"symbol": "000936"}', limit=5)

# 查询涨停池
data_query(interface="limit_up_pool", limit=10)

# 查询财联社市场情绪
data_query(interface="cls_market_emotion")

# 查询期货日线
data_query(interface="futures_daily", params_json='{"symbol": "V0"}', limit=5)

# 查询全球财经新闻（自动翻译英文）
data_query(interface="global_news_em", limit=20, translate=True)

# 查询华尔街见闻财经日历（自动翻译英文事件名）
data_query(interface="wallstreet_news", limit=30, translate=True)

# 查询美股指数日线（道琼斯）
data_query(interface="index_us_daily", params_json='{"symbol": ".DJI"}', limit=10)

# 查询全球期货实时行情
data_query(interface="futures_global_spot", limit=20)

# 查看所有可用接口
data_interfaces()
```

### 外围新闻与翻译工具

```python
# 全球财经新闻（东方财富，自动翻译英文标题/摘要）
global_news_em(limit=50, translate=True)

# 全球财经快讯（新浪）
global_news_sina(limit=20, translate=True)

# 华尔街见闻财经日历（事件/重要性/今值/预期/前值）
wallstreet_news(limit=30, translate=True)

# 上海期货交易所新闻
futures_news_shmet(limit=50, translate=True)

# 美股个股新闻（按代码过滤）
stock_us_news(symbol="AAPL", limit=30, translate=True)

# 翻译任意英文文本（金融术语词典）
translate_text(text="Federal Reserve announces interest rate hike")
```

### Reuters / Bloomberg 新闻源

```python
# 路透社相关财经新闻（网络允许时直接抓取 RSS，否则返回全球新闻）
reuters_news(limit=30, translate=True)

# 彭博社相关财经新闻（网络允许时直接抓取 RSS，否则返回全球新闻）
bloomberg_news(limit=30, translate=True)

# 彭博亿万富豪榜（网络允许时可用）
bloomberg_billionaires(limit=50)

# 搜索全球财经新闻（支持 Reuters/Bloomberg/美联储/央行等关键词）
global_news_search(keyword="美联储", limit=30)
global_news_search(keyword="Bloomberg", limit=30)
global_news_search(keyword="原油", limit=30)
```

### 专用工具

```python
# 财联社电报（标红新闻，最近1小时）
cls_telegraph(limit=20, red_only=True, hours=1)

# 涨停池
stock_limit_up_pool(limit=50)

# A股实时行情（多只）
stock_zh_a_spot(symbols="000936,600519")
```

### a-stock-data 补充信息源

```python
# 腾讯财经实时行情（PE/PB/市值/换手率/涨跌停价，不封IP）
tencent_realtime_quote(symbol="sh600519,sz000001")

# 北向资金持股明细
northbound_flow(symbol="600519")

# 个股资金流向（主力/大单/中单/小单）
stock_fund_flow(symbol="600519")

# 融资融券（沪市/深市）
margin_trading(market="sh")

# 大宗交易
block_trade()

# 股东户数变化（筹码集中度）
holder_count()

# 限售解禁日历
lockup_release()

# 研报盈利预测
research_report(symbol="600519", indicator="一致预期EPS")

# 一致预期EPS
eps_forecast(symbol="600519")

# 炸板池（曾涨停又开板）
limit_up_broken(date="20260710")

# 昨日涨停池
limit_up_previous(date="20260710")

# 强势股池（连板等）
limit_up_strong(date="20260710")

# ETF期权实时行情
option_t_quote(symbol="sh510300")

# 东财人气排行榜
hot_rank(limit=100)

# 概念板块归属
concept_belong(symbol="600519")
```

## 项目结构

```
akshare-mcp/
├── server.py             # 主服务（43个工具 + 统一调用层 + 翻译模块）
├── cls_telegraph.py      # 财联社电报独立脚本
├── run.sh                # 启动脚本
├── mcp.json              # MCP 配置示例
├── requirements.txt      # 依赖列表
├── pyproject.toml        # 项目打包配置
├── Dockerfile            # Docker 容器配置
├── docker-compose.yml    # Docker Compose 配置
└── README.md
```

## 免责声明

数据来自第三方公开接口，可能存在延迟、缺失或错误，仅供技术研究与学习使用，不构成投资建议。
