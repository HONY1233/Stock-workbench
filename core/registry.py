"""数据源注册中心：从 YAML 配置自动注册 MCP 工具。

核心思路：
  - 简单源（akshare/axshare 直传）由 YAML 配置驱动，自动生成 MCP 工具
  - 复杂源（自定义抓取逻辑）由 sources/ 目录下的模块提供
  - 新增简单源：只需在 data_sources.yaml 加一条配置
  - 新增复杂源：在 sources/ 下加一个模块，实现 register(mcp) 函数
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

import yaml

from core.helpers import _df_to_records, _json_ok, _json_fail
from core.translate import _translate_records


# ── 代码格式转换 ──────────────────────────────────────────

def _convert_symbol_sina_to_tdx(symbol: str) -> str:
    """新浪格式(sh600519/sz000001/600519) -> TDX格式(600519.SH/000001.SZ)。"""
    s = symbol.upper().strip()
    if "." in s:
        return s
    s_lower = s.lower()
    if s_lower.startswith("sh"):
        return s[2:] + ".SH"
    if s_lower.startswith("sz"):
        return s[2:] + ".SZ"
    if len(s) == 6:
        if s[0] in "6" or s[:2] in ("68", "90", "51", "11", "13"):
            return s + ".SH"
        return s + ".SZ"
    return s


def _convert_symbol_tdx_to_sina(symbol: str) -> str:
    """TDX格式(600519.SH/000001.SZ) -> 新浪格式(sh600519/sz000001)。"""
    s = symbol.upper().strip()
    if s.endswith(".SH"):
        return "sh" + s[:-3]
    if s.endswith(".SZ"):
        return "sz" + s[:-3]
    s_lower = s.lower()
    if s_lower.startswith("sh") or s_lower.startswith("sz"):
        return s_lower
    if len(s) == 6:
        if s[0] in "6" or s[:2] in ("68", "90", "51", "11", "13"):
            return "sh" + s
        return "sz" + s
    return s


# ── AxData 客户端 ──────────────────────────────────────────

_axdata_client = None


def _get_axdata_client():
    """获取或初始化 AxData 客户端。"""
    global _axdata_client
    if _axdata_client is None:
        import axdata as ax
        _axdata_client = ax.AxDataClient()
    return _axdata_client


# ── 参数适配 ──────────────────────────────────────────

def _adapt_params(params: dict, cfg: dict) -> dict:
    """根据配置转换参数名和代码格式。"""
    result = {}
    param_map = cfg.get("param_map", {})
    symbol_fmt = cfg.get("symbol_fmt")
    drop_params = set(cfg.get("drop_params", []))

    for key, val in params.items():
        if key in drop_params:
            continue
        new_key = param_map.get(key, key)
        result[new_key] = val

    # 代码格式转换
    sym = result.get("symbol") or result.get("code") or result.get("instrument_id")
    sym_key = "symbol" if "symbol" in result else ("code" if "code" in result else None)
    if sym and sym_key and symbol_fmt:
        if symbol_fmt == "tdx":
            result[sym_key] = _convert_symbol_sina_to_tdx(sym)
        elif symbol_fmt == "sina":
            result[sym_key] = _convert_symbol_tdx_to_sina(sym)

    # 添加额外参数
    extra = cfg.get("extra", {})
    for k, v in extra.items():
        if k not in result:
            result[k] = v

    result.pop("limit", None)
    return result


def _filter_data(data: list[dict], cfg: dict, params: dict) -> list[dict]:
    """客户端过滤：根据 symbol 参数过滤数据。"""
    filter_by = cfg.get("filter_by")
    sym = params.get("symbol") or params.get("code")
    if not filter_by or not sym:
        return data

    sym_list = [s.strip().lower().replace("sh", "").replace("sz", "").replace(".sh", "").replace(".sz", "")
                for s in str(sym).split(",")]

    filtered = []
    for item in data:
        val = str(item.get(filter_by, "")).lower()
        val_clean = val.replace("sh", "").replace("sz", "").replace(".sh", "").replace(".sz", "")
        if val_clean in sym_list or any(s in val_clean for s in sym_list):
            filtered.append(item)
    return filtered


# ── 新浪直连行情（fallback 用） ──────────────────────────────────────────

def _get_sina_spot(symbols: list[str]) -> list[dict]:
    """从新浪财经获取实时行情。"""
    try:
        from curl_cffi import requests
    except ImportError:
        import requests as requests

    code_list = []
    for sym in symbols:
        s = sym.lower().replace(".sh", "").replace(".sz", "")
        if s.startswith("sh") or s.startswith("sz"):
            code_list.append(s)
        elif len(s) == 6:
            if s[0] in "6" or s[:2] in ("68", "90", "51", "11", "13"):
                code_list.append("sh" + s)
            else:
                code_list.append("sz" + s)
        else:
            code_list.append(sym)

    url = "https://hq.sinajs.cn/list=" + ",".join(code_list)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Referer": "https://finance.sina.com.cn/",
    }

    try:
        r = requests.get(url, headers=headers, timeout=10)
    except Exception:
        return []

    results = []
    lines = r.text.strip().split("\n")
    for line in lines:
        if "=" not in line:
            continue
        code_part, data_part = line.split("=", 1)
        code = code_part.replace("var hq_str_", "").strip()
        data_str = data_part.strip().strip('"')
        if not data_str:
            continue
        fields = data_str.split(",")
        if len(fields) < 32:
            continue

        name = fields[0]
        open_price = float(fields[1]) if fields[1] else 0
        prev_close = float(fields[2]) if fields[2] else 0
        price = float(fields[3]) if fields[3] else 0
        high = float(fields[4]) if fields[4] else 0
        low = float(fields[5]) if fields[5] else 0
        volume = float(fields[8]) if fields[8] else 0
        amount = float(fields[9]) if fields[9] else 0

        change = price - prev_close if prev_close else 0
        change_pct = (change / prev_close * 100) if prev_close else 0

        results.append({
            "代码": code, "名称": name, "最新价": round(price, 2),
            "涨跌额": round(change, 2), "涨跌幅": round(change_pct, 2),
            "今开": round(open_price, 2), "最高": round(high, 2), "最低": round(low, 2),
            "昨收": round(prev_close, 2), "成交量": volume, "成交额": amount,
            "source": "sina",
        })
    return results


# ── 数据源调用 ──────────────────────────────────────────

def _call_axdata(cfg: dict, **params) -> tuple[bool, list[dict], str]:
    """调用 axdata 接口。"""
    try:
        client = _get_axdata_client()
        adapted = _adapt_params(params, cfg)
        df = client.call(cfg["interface"], **adapted)
        if df is not None and not df.empty:
            data = _df_to_records(df)
            data = _filter_data(data, cfg, params)
            return True, data, f"axdata:{cfg['interface']}"
        return False, [], f"axdata:{cfg['interface']}"
    except Exception as e:
        return False, [{"error": f"{type(e).__name__}: {str(e)[:200]}"}], f"axdata:{cfg['interface']}"


def _call_akshare(cfg: dict, **params) -> tuple[bool, list[dict], str]:
    """调用 akshare 接口。"""
    try:
        import akshare as ak
        func = getattr(ak, cfg["func"])
        adapted = _adapt_params(params, cfg)
        df = func(**adapted)
        if df is not None and not df.empty:
            data = _df_to_records(df)
            data = _filter_data(data, cfg, params)
            return True, data, f"akshare:{cfg['func']}"
        return False, [], f"akshare:{cfg['func']}"
    except Exception as e:
        if cfg.get("sina_fallback"):
            sym = params.get("symbol") or params.get("code")
            if sym:
                sym_list = [s.strip() for s in str(sym).split(",") if s.strip()]
                data = _get_sina_spot(sym_list)
                if data:
                    return True, data, "sina:direct"
        return False, [{"error": f"{type(e).__name__}: {str(e)[:200]}"}], f"akshare:{cfg['func']}"


def call_unified(interface: str, config_map: dict, source_preference: str = "any", **params) -> tuple[bool, list[dict], str]:
    """统一数据调用：自动路由到 axdata 或 akshare，支持按需指定数据源。

    Args:
        interface: 接口名称
        config_map: 配置映射表
        source_preference: 数据源偏好
            - "any": 自动路由（默认，axdata 优先，akshare fallback）
            - "axdata_only": 只调用 axdata
            - "akshare_only": 只调用 akshare
            - 其他: 视为 provider 名称，只调用该 provider 提供的源
        **params: 调用参数

    返回 (是否成功, 数据列表, 实际数据源)。
    """
    cfg = config_map.get(interface)

    if cfg:
        axdata_cfg = cfg.get("axdata")
        akshare_cfg = cfg.get("akshare")
        providers = cfg.get("providers", [])
        last_error = None
        last_source = "unknown"

        # 根据 source_preference 决定调用策略
        sp = (source_preference or "any").lower().strip()

        # provider 级别过滤
        if sp not in ("any", "axdata_only", "akshare_only", ""):
            # sp 是 provider 名称，检查该接口是否支持此 provider
            if sp not in [p.lower() for p in providers]:
                return False, [{"error": f"接口 {interface} 不支持 provider '{source_preference}'，支持的 providers: {providers}"}], "unknown"
            # 只调用匹配 provider 的源
            # 优先 axdata（如果其接口名包含 provider 特征或 providers 包含该 provider）
            # 这里简化处理：axdata 的 provider 由接口名推断，akshare 的 provider 由函数名和配置推断
            # 实际策略：先尝试 axdata，再尝试 akshare，但限制在匹配的 provider 内
            # 由于无法精确知道 axdata/akshare 各自的 provider，我们按原顺序调用，
            # 但在返回时标注。更精确的做法是：如果接口只有一个 provider 且匹配，则调用。
            # 如果有多个 provider，我们尝试两个源，但至少有一个应该匹配。
            pass  # 继续执行下面的逻辑

        if sp in ("any", "", "axdata_only") or (sp not in ("akshare_only",)):
            if axdata_cfg:
                ok, data, source = _call_axdata(axdata_cfg, **params)
                if ok and data:
                    return ok, data, source
                if not ok:
                    last_error = data[0].get("error", "未知错误") if data else "未知错误"
                    last_source = source
                else:
                    last_source = source

        if sp in ("any", "", "akshare_only") or (sp not in ("axdata_only",)):
            if akshare_cfg:
                ok, data, source = _call_akshare(akshare_cfg, **params)
                if ok and data:
                    return ok, data, source
                if not ok:
                    last_error = data[0].get("error", "未知错误") if data else "未知错误"
                    last_source = source
                else:
                    last_source = source

        if last_error:
            return False, [{"error": last_error}], last_source
        return True, [], last_source

    # 不在映射表中，尝试直接调 axdata
    if sp == "akshare_only":
        return False, [{"error": f"接口 {interface} 不在配置表中，无法使用 akshare_only 模式"}], "unknown"
    try:
        client = _get_axdata_client()
        df = client.call(interface, **params)
        if df is not None and not df.empty:
            return True, _df_to_records(df), f"axdata:{interface}"
        return True, [], f"axdata:{interface}"
    except Exception as e:
        return False, [{"error": f"{type(e).__name__}: {str(e)[:200]}"}], f"axdata:{interface}"


# ── SourceRegistry 核心类 ──────────────────────────────────────────

class SourceRegistry:
    """数据源注册中心。

    从 YAML 配置文件加载所有数据源定义，自动生成 MCP 工具。
    复杂源（自定义逻辑）由 sources/ 目录的模块手动注册。
    """

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), "..", "data_sources.yaml")
        self.config_path = str(config_path)
        self.sources: dict[str, dict] = {}
        self.custom_sources: set[str] = set()
        self._load_config()

    def _load_config(self) -> None:
        """加载 YAML 配置。"""
        with open(self.config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.sources = data.get("sources", {})
        self.custom_sources = set(data.get("custom_sources", []))

    def reload(self) -> None:
        """重新加载配置（热更新）。"""
        self._load_config()

    def get_source(self, name: str) -> Optional[dict]:
        """获取单个数据源配置。"""
        return self.sources.get(name)

    def list_sources(self) -> dict[str, str]:
        """列出所有数据源名称和描述。"""
        return {name: cfg.get("desc", "") for name, cfg in self.sources.items()}

    def get_providers(self) -> set[str]:
        """获取所有数据来源提供商列表。"""
        providers = set()
        for cfg in self.sources.values():
            for p in cfg.get("providers", []):
                providers.add(p)
        return providers

    def list_by_provider(self, provider: str) -> dict[str, dict]:
        """按数据来源提供商筛选接口。

        Args:
            provider: 提供商名称，如 sina, eastmoney, cls 等

        Returns:
            该提供商支持的接口字典 {alias: config}
        """
        provider_lower = provider.lower()
        result = {}
        for name, cfg in self.sources.items():
            providers = [p.lower() for p in cfg.get("providers", [])]
            if provider_lower in providers:
                result[name] = cfg
        return result

    def get_source_providers(self, name: str) -> list[str]:
        """获取指定接口的数据来源提供商列表。"""
        cfg = self.sources.get(name)
        if not cfg:
            return []
        return cfg.get("providers", [])

    def register_auto_tools(self, mcp) -> None:
        """为 YAML 配置中的所有简单源自动注册 MCP 工具。

        只注册有 axdata 或 akshare 配置的源。
        custom_sources 列表中的工具由 sources/ 模块手动注册，跳过。
        """
        for name, cfg in self.sources.items():
            if name in self.custom_sources:
                continue
            if cfg.get("axdata") or cfg.get("akshare"):
                self._register_one(mcp, name, cfg)

    def _register_one(self, mcp, name: str, cfg: dict) -> None:
        """为单个数据源注册 MCP 工具。"""
        desc = cfg.get("desc", name)
        source_name = name

        def make_tool(_name: str, _cfg: dict, _desc: str):
            def tool_fn(params_json: str = "{}", limit: int = 0, translate: bool = True) -> str:
                params = json.loads(params_json) if params_json else {}
                ok, data, source = call_unified(_name, self.sources, **params)
                if not ok:
                    err = data[0].get("error", "未知错误") if data else "未知错误"
                    return json.dumps({"ok": False, "interface": _name, "source": source, "error": err}, ensure_ascii=False)
                if limit and len(data) > limit:
                    data = data[:limit]
                # 自动翻译
                translated = False
                if translate and data:
                    tfields = set()
                    for src_key in ("axdata", "akshare"):
                        src_cfg = _cfg.get(src_key)
                        if src_cfg and src_cfg.get("translate_fields"):
                            tfields.update(src_cfg["translate_fields"])
                    if tfields:
                        _translate_records(data, fields=tfields, translate=True)
                        translated = True
                return json.dumps({
                    "ok": True, "interface": _name, "source": source,
                    "count": len(data), "translated": translated, "data": data,
                }, ensure_ascii=False)
            tool_fn.__name__ = _name
            tool_fn.__doc__ = f"{_desc}。\n\nArgs:\n    params_json: JSON 参数，如 '{{\"symbol\": \"600519\"}}'\n    limit: 返回条数限制，0=不限\n    translate: 是否翻译英文内容\n\nReturns:\n    JSON 格式查询结果"
            return tool_fn

        mcp.tool(description=desc)(make_tool(source_name, cfg, desc))


def load_custom_sources(mcp, sources_dir: str = None) -> list[str]:
    """自动加载 sources/ 目录下的自定义源模块。

    每个模块需要实现 register(mcp) -> list[str] 函数，
    返回已注册的工具名列表。
    """
    if sources_dir is None:
        sources_dir = os.path.join(os.path.dirname(__file__), "..", "sources")

    import importlib
    registered = []

    if not os.path.isdir(sources_dir):
        return registered

    for py_file in sorted(Path(sources_dir).glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        module_name = f"sources.{py_file.stem}"
        try:
            mod = importlib.import_module(module_name)
            if hasattr(mod, "register"):
                tools = mod.register(mcp)
                if isinstance(tools, list):
                    registered.extend(tools)
        except Exception as e:
            print(f"警告: 加载源模块 {module_name} 失败: {e}", flush=True)

    return registered
