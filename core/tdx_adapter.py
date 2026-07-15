"""通达信数据源适配器：封装 opentdx 库，提供统一的行情数据接口。

设计思路：
  - 作为 Stock-workbench 的新数据源 provider
  - 支持A股/港股/美股/期货的实时行情、K线、技术指标
  - 无需本地安装通达信，直接连接公开行情服务器
  - 作为 akshare/axdata 的备选数据源

依赖：
  pip install opentdx  (或从 https://github.com/rainx/pytdx 安装)
"""
from __future__ import annotations

import json
from typing import Optional, Any
from dataclasses import dataclass


@dataclass
class TDXConfig:
    """通达信连接配置。"""
    host: str = "119.147.212.81"
    port: int = 7709
    timeout: int = 10


class TDXAdapter:
    """通达信数据源适配器。"""

    def __init__(self, config: Optional[TDXConfig] = None):
        self.config = config or TDXConfig()
        self._client = None

    def _get_client(self):
        """获取或初始化 TDX 客户端。"""
        if self._client is None:
            try:
                from pytdx.hq import TdxHq_API
                self._client = TdxHq_API()
                connected = self._client.connect(self.config.host, self.config.port)
                if not connected:
                    raise ConnectionError(f"无法连接到 TDX 服务器 {self.config.host}:{self.config.port}")
            except ImportError:
                raise ImportError("请安装 opentdx: pip install opentdx")
        return self._client

    def close(self):
        """关闭连接。"""
        if self._client:
            try:
                self._client.disconnect()
            except Exception:
                pass
            self._client = None

    # ── 行情数据 ──────────────────────────────────────────

    def get_quotes(self, stock_codes: list[str], market: int = None) -> list[dict]:
        """获取股票实时行情。

        Args:
            stock_codes: 股票代码列表，如 ['600519', '000001']
            market: 市场代码，0=深市，1=沪市。不指定则自动判断

        Returns:
            行情数据列表
        """
        try:
            client = self._get_client()
            results = []

            for code in stock_codes:
                # 自动判断市场
                if market is None:
                    m = 1 if code.startswith(('6', '9', '5')) else 0
                else:
                    m = market

                data = client.get_security_quotes([(m, code)])
                if data:
                    for item in data:
                        results.append({
                            "code": item.get("code", code),
                            "name": item.get("name", ""),
                            "price": item.get("price", 0),
                            "open": item.get("open", 0),
                            "high": item.get("high", 0),
                            "low": item.get("low", 0),
                            "last_close": item.get("last_close", 0),
                            "volume": item.get("vol", 0),
                            "amount": item.get("amount", 0),
                            "bid1": item.get("bid1", 0),
                            "ask1": item.get("ask1", 0),
                            "bid_vol1": item.get("bid_vol1", 0),
                            "ask_vol1": item.get("ask_vol1", 0),
                            "source": "tdx",
                        })

            return results
        except Exception as e:
            return [{"error": f"{type(e).__name__}: {str(e)[:200]}"}]

    def get_kline(
        self,
        stock_code: str,
        market: int = None,
        start: int = 0,
        count: int = 100,
        kline_type: int = 8,  # 8=日线，9=周线，5=月线，0=5分钟，1=15分钟...
    ) -> list[dict]:
        """获取 K 线数据。

        Args:
            stock_code: 股票代码
            market: 市场代码，0=深市，1=沪市
            start: 起始位置
            count: 数据条数
            kline_type: K线类型

        Returns:
            K线数据列表
        """
        try:
            client = self._get_client()

            if market is None:
                market = 1 if stock_code.startswith(('6', '9', '5')) else 0

            data = client.get_security_bars(kline_type, market, stock_code, start, count)
            if not data:
                return []

            results = []
            for item in data:
                results.append({
                    "datetime": item.get("datetime", ""),
                    "open": item.get("open", 0),
                    "high": item.get("high", 0),
                    "low": item.get("low", 0),
                    "close": item.get("close", 0),
                    "volume": item.get("vol", 0),
                    "amount": item.get("amount", 0),
                    "code": stock_code,
                    "source": "tdx",
                })

            return results
        except Exception as e:
            return [{"error": f"{type(e).__name__}: {str(e)[:200]}"}]

    def get_index_kline(
        self,
        index_code: str,
        market: int = None,
        start: int = 0,
        count: int = 100,
        kline_type: int = 8,
    ) -> list[dict]:
        """获取指数 K 线数据。"""
        try:
            client = self._get_client()

            if market is None:
                market = 1 if index_code.startswith(('000', '88')) else 0

            data = client.get_index_bars(kline_type, market, index_code, start, count)
            if not data:
                return []

            results = []
            for item in data:
                results.append({
                    "datetime": item.get("datetime", ""),
                    "open": item.get("open", 0),
                    "high": item.get("high", 0),
                    "low": item.get("low", 0),
                    "close": item.get("close", 0),
                    "volume": item.get("vol", 0),
                    "amount": item.get("amount", 0),
                    "code": index_code,
                    "source": "tdx",
                })

            return results
        except Exception as e:
            return [{"error": f"{type(e).__name__}: {str(e)[:200]}"}]

    def get_tick_data(self, stock_code: str, market: int = None) -> list[dict]:
        """获取分时数据。"""
        try:
            client = self._get_client()

            if market is None:
                market = 1 if stock_code.startswith(('6', '9', '5')) else 0

            data = client.get_security_quotes([(market, stock_code)])
            if not data:
                return []

            # 获取分时成交
            ticks = client.get_transaction_data(market, stock_code, 0, 50)
            if not ticks:
                return []

            results = []
            for item in ticks:
                results.append({
                    "time": item.get("time", ""),
                    "price": item.get("price", 0),
                    "volume": item.get("vol", 0),
                    "num": item.get("num", 0),
                    "buyorsell": item.get("buyorsell", 0),
                    "code": stock_code,
                    "source": "tdx",
                })

            return results
        except Exception as e:
            return [{"error": f"{type(e).__name__}: {str(e)[:200]}"}]

    # ── 板块数据 ──────────────────────────────────────────

    def get_stock_list(self, market: int = 1) -> list[dict]:
        """获取股票列表。

        Args:
            market: 市场代码，0=深市，1=沪市

        Returns:
            股票列表
        """
        try:
            client = self._get_client()
            data = client.get_security_list(market, 0)
            if not data:
                return []

            results = []
            for item in data:
                results.append({
                    "code": item.get("code", ""),
                    "name": item.get("name", ""),
                    "source": "tdx",
                })

            return results
        except Exception as e:
            return [{"error": f"{type(e).__name__}: {str(e)[:200]}"}]

    def get_index_list(self) -> list[dict]:
        """获取指数列表。"""
        try:
            client = self._get_client()
            results = []

            # 沪市指数
            data = client.get_security_list(1, 0)
            if data:
                for item in data:
                    code = item.get("code", "")
                    if code.startswith("000") or code.startswith("88"):
                        results.append({
                            "code": code,
                            "name": item.get("name", ""),
                            "market": "sh",
                            "source": "tdx",
                        })

            # 深市指数
            data = client.get_security_list(0, 0)
            if data:
                for item in data:
                    code = item.get("code", "")
                    if code.startswith("399") or code.startswith("88"):
                        results.append({
                            "code": code,
                            "name": item.get("name", ""),
                            "market": "sz",
                            "source": "tdx",
                        })

            return results
        except Exception as e:
            return [{"error": f"{type(e).__name__}: {str(e)[:200]}"}]

    # ── F10 数据 ──────────────────────────────────────────

    def get_f10_info(self, stock_code: str, market: int = None) -> dict:
        """获取 F10 基本信息。"""
        try:
            client = self._get_client()

            if market is None:
                market = 1 if stock_code.startswith(('6', '9', '5')) else 0

            data = client.get_finance_info(market, stock_code)
            if not data:
                return {"error": "无数据"}

            return {
                "code": stock_code,
                "name": data.get("name", ""),
                "total_shares": data.get("total_shares", 0),
                "float_shares": data.get("float_shares", 0),
                "pe_ratio": data.get("pe_ratio", 0),
                "pb_ratio": data.get("pb_ratio", 0),
                "source": "tdx",
            }
        except Exception as e:
            return {"error": f"{type(e).__name__}: {str(e)[:200]}"}


# 全局实例
_tdx_adapter: Optional[TDXAdapter] = None


def get_tdx_adapter() -> TDXAdapter:
    """获取全局 TDX 适配器实例。"""
    global _tdx_adapter
    if _tdx_adapter is None:
        _tdx_adapter = TDXAdapter()
    return _tdx_adapter


def call_tdx(interface: str, **params) -> tuple[bool, list[dict], str]:
    """统一的 TDX 调用入口。

    Args:
        interface: 接口名称
        **params: 调用参数

    Returns:
        (是否成功, 数据列表, 数据源标识)
    """
    adapter = get_tdx_adapter()

    interface_map = {
        "stock_quotes": adapter.get_quotes,
        "stock_kline": adapter.get_kline,
        "index_kline": adapter.get_index_kline,
        "tick_data": adapter.get_tick_data,
        "stock_list": adapter.get_stock_list,
        "index_list": adapter.get_index_list,
        "f10_info": adapter.get_f10_info,
    }

    if interface not in interface_map:
        return False, [{"error": f"TDX 接口 {interface} 不存在，支持的接口: {list(interface_map.keys())}"}], "tdx"

    try:
        data = interface_map[interface](**params)
        if data and isinstance(data, list) and data[0].get("error"):
            return False, data, f"tdx:{interface}"
        return True, data, f"tdx:{interface}"
    except Exception as e:
        return False, [{"error": f"{type(e).__name__}: {str(e)[:200]}"}], f"tdx:{interface}"