# -*- coding: utf-8 -*-
"""批量生成 6 个独立 MCP 的脚本。"""
import os
import shutil
import json

BASE = r"E:\Trae data\Stock-workbench\mcps"
TEMPLATE = os.path.join(BASE, "_template")

MCPS = {
    "stock-mcp": {
        "display_name": "stock-mcp",
        "description": "A股行情 MCP 服务器",
        "port": 8001,
        "sources": [
            "stock_daily", "stock_realtime", "index_daily", "index_realtime",
            "etf_daily", "etf_realtime", "limit_up_pool", "limit_down_pool",
            "sector_realtime", "market_index_realtime",
            "lhb_daily", "lhb_institution",
            "limit_up_broken", "limit_up_previous", "limit_up_strong",
            "hot_rank", "concept_belong", "etf_spot",
        ],
        "providers": ["sina", "eastmoney", "ths", "tencent", "tdx"],
        "custom_sources": [],  # 暂不包含自定义复杂源
    },
    "news-mcp": {
        "display_name": "news-mcp",
        "description": "财经新闻 MCP 服务器",
        "port": 8002,
        "sources": [
            "cls_telegraph", "cls_market_emotion", "cls_limit_up_pool",
            "cls_sector_heat", "cls_market_wind", "cls_market_mainline",
            "kph_market_emotion",
            "global_news_em", "global_news_sina", "global_news_ths",
        ],
        "providers": ["cls", "kph", "eastmoney", "sina", "ths"],
        "custom_sources": ["news"],
    },
    "finance-mcp": {
        "display_name": "finance-mcp",
        "description": "资金财务 MCP 服务器",
        "port": 8003,
        "sources": [
            "northbound_flow", "stock_fund_flow", "margin_trading",
            "block_trade", "holder_count", "lockup_release",
            "research_report", "eps_forecast",
        ],
        "providers": ["eastmoney", "sse", "ths"],
        "custom_sources": [],
    },
    "derivatives-mcp": {
        "display_name": "derivatives-mcp",
        "description": "衍生品行情 MCP 服务器",
        "port": 8004,
        "sources": [
            "futures_daily", "futures_realtime",
            "option_commodity_list", "option_cffex_hs300_list",
            "option_t_quote",
        ],
        "providers": ["sina", "eastmoney"],
        "custom_sources": [],
    },
    "company-mcp": {
        "display_name": "company-mcp",
        "description": "公司信息 MCP 服务器",
        "port": 8005,
        "sources": [
            "cninfo_announcements", "stock_profile_cninfo", "stock_dividend_cninfo",
        ],
        "providers": ["cninfo"],
        "custom_sources": ["cninfo"],
    },
    "global-mcp": {
        "display_name": "global-mcp",
        "description": "国际市场 MCP 服务器",
        "port": 8006,
        "sources": [
            "index_us_daily", "index_hk_daily", "index_global_list",
            "futures_global_spot",
        ],
        "providers": ["sina", "eastmoney", "bloomberg", "reuters"],
        "custom_sources": ["international"],
    },
}

# 读取原始 data_sources.yaml
import yaml
ORIGINAL_YAML = r"E:\Trae data\Stock-workbench\data_sources.yaml"
with open(ORIGINAL_YAML, "r", encoding="utf-8") as f:
    original_data = yaml.safe_load(f)

all_providers = original_data.get("providers", {})
all_sources = original_data.get("sources", {})

# 读取原始自定义源
ORIGINAL_SOURCES_DIR = r"E:\Trae data\Stock-workbench\sources"

def generate_mcp(mcp_name: str, config: dict):
    mcp_dir = os.path.join(BASE, mcp_name)
    
    # 复制 core/ 目录
    core_dir = os.path.join(mcp_dir, "core")
    if os.path.exists(core_dir):
        shutil.rmtree(core_dir)
    shutil.copytree(os.path.join(TEMPLATE, "core"), core_dir)
    
    # 生成 data_sources.yaml
    selected_providers = {}
    for p in config["providers"]:
        if p in all_providers:
            selected_providers[p] = all_providers[p]
    
    selected_sources = {}
    for s in config["sources"]:
        if s in all_sources:
            selected_sources[s] = all_sources[s]
    
    yaml_data = {
        "providers": selected_providers,
        "sources": selected_sources,
    }
    
    yaml_path = os.path.join(mcp_dir, "data_sources.yaml")
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(yaml_data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    
    # 复制 requirements.txt
    shutil.copy(
        os.path.join(TEMPLATE, "requirements.txt"),
        os.path.join(mcp_dir, "requirements.txt"),
    )
    
    # 生成 server.py
    with open(os.path.join(TEMPLATE, "server_template.py"), "r", encoding="utf-8") as f:
        server_tpl = f.read()
    
    server_code = server_tpl.replace("MCP_SERVER_NAME", config["display_name"])
    server_code = server_code.replace("8000", str(config["port"]))
    
    # 处理自定义源
    if config["custom_sources"]:
        sources_dir = os.path.join(mcp_dir, "sources")
        os.makedirs(sources_dir, exist_ok=True)
        with open(os.path.join(sources_dir, "__init__.py"), "w") as f:
            f.write("")
        
        custom_imports = []
        custom_loads = []
        
        for cs in config["custom_sources"]:
            src_file = os.path.join(ORIGINAL_SOURCES_DIR, f"{cs}.py")
            if os.path.exists(src_file):
                dst_file = os.path.join(sources_dir, f"{cs}.py")
                shutil.copy(src_file, dst_file)
                custom_imports.append(f"from sources.{cs} import register as register_{cs}")
                custom_loads.append(f"register_{cs}(mcp)")
        
        # 替换 CUSTOM_SOURCES_LOAD 标记
        custom_block = "\n# 加载自定义源\n" + "\n".join(custom_imports) + "\n\n" + "\n".join(f"_ = {fn}" for fn in custom_loads) + "\n"
        server_code = server_code.replace("# CUSTOM_SOURCES_LOAD", custom_block)
    else:
        server_code = server_code.replace("# CUSTOM_SOURCES_LOAD", "")
    
    server_path = os.path.join(mcp_dir, "server.py")
    with open(server_path, "w", encoding="utf-8") as f:
        f.write(server_code)
    
    # 生成 .trae/mcp.json
    mcp_json = {
        "mcpServers": {
            mcp_name: {
                "command": "E:\\python\\python.exe",
                "args": [os.path.join(mcp_dir, "server.py")],
                "env": {
                    "START_MCP_TIMEOUT_MS": "60000",
                    "RUN_MCP_TIMEOUT_MS": "120000",
                },
            }
        }
    }
    
    trae_dir = os.path.join(mcp_dir, ".trae")
    os.makedirs(trae_dir, exist_ok=True)
    mcp_json_path = os.path.join(trae_dir, "mcp.json")
    with open(mcp_json_path, "w", encoding="utf-8") as f:
        json.dump(mcp_json, f, ensure_ascii=False, indent=2)
    
    print(f"  ✅ {mcp_name}: {len(config['sources'])} 个 YAML 源 + {len(config['custom_sources'])} 个自定义源")


if __name__ == "__main__":
    print("开始生成 6 个独立 MCP...")
    for name, cfg in MCPS.items():
        generate_mcp(name, cfg)
    print("全部生成完成！")
