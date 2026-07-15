"""数据源注册中心：从 YAML 配置自动注册 MCP 工具。"""
from __future__ import annotations

import json
import os
import time as _time
from pathlib import Path
from typing import Optional

import yaml

from core.helpers import _df_to_records
from core.translate import _translate_records


def _convert_symbol_sina_to_tdx(symbol: str) -> str:
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


_axdata_client = None


def _get_axdata_client():
    global _axdata_client
    if _axdata_client is None:
        import axdata as ax
        _axdata_client = ax.AxDataClient()
    return _axdata_client


def _adapt_params(params: dict, cfg: dict) -> dict:
    result = {}
    param_map = cfg.get("param_map", {})
    symbol_fmt = cfg.get("symbol_fmt")
    drop_params = set(cfg.get("drop_params", []))

    for key, val in params.items():
        if key in drop_params:
            continue
        new_key = param_map.get(key, key)
        result[new_key] = val

    sym = result.get("symbol") or result.get("code") or result.get("instrument_id")
    sym_key = "symbol" if "symbol" in result else ("code" if "code" in result else None)
    if sym and sym_key and symbol_fmt:
        if symbol_fmt == "tdx":
            result[sym_key] = _convert_symbol_sina_to_tdx(sym)
        elif symbol_fmt == "sina":
            result[sym_key] = _convert_symbol_tdx_to_sina(sym)

    extra = cfg.get("extra", {})
    for k, v in extra.items():
        if k not in result:
            result[k] = v

    result.pop("limit", None)
    return result


def _filter_data(data: list[dict], cfg: dict, params: dict) -> list[dict]:
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


def _get_sina_spot(symbols: list[str]) -> list[dict]:
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


def _call_axdata(cfg: dict, **params) -> tuple[bool, list[dict], str]:
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
    max_retries = 2
    last_exc = None

    func_candidates = [cfg["func"]]
    if cfg.get("fallback_func"):
        func_candidates.append(cfg["fallback_func"])

    for func_name in func_candidates:
        for attempt in range(max_retries + 1):
            try:
                import akshare as ak
                import pandas as pd

                func = getattr(ak, func_name)
                adapted = _adapt_params(params, cfg)

                old_opt = pd.get_option("future.infer_string")
                try:
                    pd.set_option("future.infer_string", False)
                    df = func(**adapted)
                finally:
                    pd.set_option("future.infer_string", old_opt)

                if df is not None and not df.empty:
                    data = _df_to_records(df)
                    data = _filter_data(data, cfg, params)
                    return True, data, f"akshare:{func_name}"
                last_exc = None
                break
            except Exception as e:
                last_exc = e
                is_network_err = any(
                    kw in type(e).__name__
                    for kw in ("Connection", "Timeout", "Remote", "HTTP")
                ) or any(
                    kw in str(e)[:200]
                    for kw in ("Connection", "Timeout", "Remote", "reset", "refused")
                )
                if is_network_err and attempt < max_retries:
                    _time.sleep(1.0 * (attempt + 1))
                    continue
                break

    if cfg.get("sina_fallback"):
        sym = params.get("symbol") or params.get("code")
        if sym:
            sym_list = [s.strip() for s in str(sym).split(",") if s.strip()]
            data = _get_sina_spot(sym_list)
            if data:
                return True, data, "sina:direct"

    if last_exc and "bloomberg" in str(last_exc).lower():
        return False, [{"error": "彭博社接口国内网络不可达，建议使用代理或更换数据源"}], f"akshare:{cfg['func']}"
    if last_exc:
        return False, [{"error": f"{type(last_exc).__name__}: {str(last_exc)[:200]}"}], f"akshare:{cfg['func']}"
    return False, [], f"akshare:{cfg['func']}"


def _call_source(name: str, sources_map: dict, **params) -> tuple[bool, list[dict], str]:
    cfg = sources_map.get(name)
    if not cfg:
        return False, [{"error": f"接口 '{name}' 不存在"}], "unknown"

    last_error = None
    last_source = "unknown"

    axdata_cfg = cfg.get("axdata")
    akshare_cfg = cfg.get("akshare")

    if axdata_cfg:
        ok, data, source = _call_axdata(axdata_cfg, **params)
        if ok and data:
            return ok, data, source
        if not ok:
            last_error = data[0].get("error", "未知错误") if data else "未知错误"
            last_source = source
        else:
            last_source = source

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


class SourceRegistry:
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), "..", "data_sources.yaml")
        self.config_path = str(config_path)
        self.sources: dict[str, dict] = {}
        self._load_config()

    def _load_config(self) -> None:
        with open(self.config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.sources = data.get("sources", {})

    def reload(self) -> None:
        self._load_config()

    def list_sources(self) -> dict[str, str]:
        return {name: cfg.get("desc", "") for name, cfg in self.sources.items()}

    def register_auto_tools(self, mcp) -> None:
        for name, cfg in self.sources.items():
            if cfg.get("axdata") or cfg.get("akshare"):
                self._register_one(mcp, name, cfg)

    def _register_one(self, mcp, name: str, cfg: dict) -> None:
        desc = cfg.get("desc", name)

        def make_tool(_name: str, _cfg: dict, _desc: str):
            def tool_fn(params_json: str = "{}", limit: int = 0, translate: bool = True) -> str:
                params = json.loads(params_json) if params_json else {}
                ok, data, source = _call_source(_name, self.sources, **params)
                if not ok:
                    err = data[0].get("error", "未知错误") if data else "未知错误"
                    return json.dumps({"ok": False, "interface": _name, "source": source, "error": err}, ensure_ascii=False)
                if limit and len(data) > limit:
                    data = data[:limit]
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
            tool_fn.__doc__ = f"{_desc}。\n\nArgs:\n    params_json: JSON 参数\n    limit: 返回条数限制，0=不限\n    translate: 是否翻译英文内容\n\nReturns:\n    JSON 格式查询结果"
            return tool_fn

        mcp.tool(description=desc)(make_tool(name, cfg, desc))
