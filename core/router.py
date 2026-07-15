"""路由层：根据接口名和数据源偏好，路由到正确的信息源。

设计思路：
  - 将路由逻辑从注册中心解耦
  - 支持三种路由模式：
    1. 自动路由（any）：按优先级尝试各数据源
    2. 指定库路由（axdata_only/akshare_only）：只调用指定库
    3. 指定 provider 路由：只调用该 provider 的接口
  - 路由时根据 provider 定义查找匹配的源，无需从接口名推断
"""
from __future__ import annotations

from typing import Any, Optional, Tuple

from core.providers import Provider, get_provider, infer_provider_from_name


class RouteResult:
    """路由结果。"""

    def __init__(
        self,
        success: bool,
        data: list[dict],
        provider: str = "unknown",
        source: str = "unknown",
        error: str = "",
    ):
        self.success = success
        self.data = data
        self.provider = provider
        self.source = source
        self.error = error

    def to_tuple(self) -> tuple[bool, list[dict], str]:
        """转为兼容旧接口的 tuple 格式。"""
        return self.success, self.data, self.source


class Router:
    """数据路由引擎。"""

    def __init__(self, sources_config: dict, provider_registry: dict[str, Provider]):
        self.sources_config = sources_config
        self.provider_registry = provider_registry

    def resolve_interface(self, interface: str) -> Optional[dict]:
        """解析接口配置。"""
        return self.sources_config.get(interface)

    def get_interface_providers(self, interface: str) -> list[str]:
        """获取接口支持的 provider 列表。"""
        cfg = self.resolve_interface(interface)
        if not cfg:
            return []

        providers = []

        # 优先使用配置中的 providers 字段
        if "providers" in cfg:
            return [p.lower() for p in cfg["providers"]]

        # 从 axdata 接口名推断
        axdata_iface = cfg.get("axdata", {}).get("interface", "") if cfg.get("axdata") else ""
        if axdata_iface:
            pid = infer_provider_from_name(axdata_iface)
            if pid:
                providers.append(pid)

        # 从 akshare 函数名推断
        ak_func = cfg.get("akshare", {}).get("func", "") if cfg.get("akshare") else ""
        if ak_func:
            pid = infer_provider_from_name(ak_func)
            if pid and pid not in providers:
                providers.append(pid)

        return providers

    def route(
        self,
        interface: str,
        source_preference: str = "any",
        **params,
    ) -> RouteResult:
        """路由到合适的数据源。

        Args:
            interface: 接口名称
            source_preference: 数据源偏好
                - "any": 自动路由（axdata 优先，akshare fallback）
                - "axdata_only": 只调用 axdata
                - "akshare_only": 只调用 akshare
                - provider ID: 只调用该 provider 的接口
            **params: 调用参数

        Returns:
            RouteResult 对象
        """
        cfg = self.resolve_interface(interface)
        if not cfg:
            return RouteResult(
                success=False, data=[], error=f"接口 {interface} 不存在"
            )

        sp = (source_preference or "any").lower().strip()
        interface_providers = self.get_interface_providers(interface)
        axdata_cfg = cfg.get("axdata")
        akshare_cfg = cfg.get("akshare")

        # 指定 provider 路由
        if sp not in ("any", "axdata_only", "akshare_only", ""):
            target_provider = sp
            if target_provider not in interface_providers:
                return RouteResult(
                    success=False, data=[],
                    error=f"接口 {interface} 不支持 provider '{target_provider}'，支持的: {interface_providers}"
                )

            # 只调用匹配 provider 的源
            if axdata_cfg:
                ax_pid = infer_provider_from_name(axdata_cfg["interface"])
                if ax_pid == target_provider:
                    ok, data, source = self._call_source("axdata", axdata_cfg, **params)
                    if ok:
                        return RouteResult(success=True, data=data, provider=target_provider, source=source)

            if akshare_cfg:
                ak_pid = infer_provider_from_name(akshare_cfg["func"])
                if ak_pid == target_provider:
                    ok, data, source = self._call_source("akshare", akshare_cfg, **params)
                    if ok:
                        return RouteResult(success=True, data=data, provider=target_provider, source=source)

            return RouteResult(
                success=False, data=[], provider=target_provider,
                error=f"provider '{target_provider}' 的接口调用失败"
            )

        # 自动路由或指定库路由
        last_error = None
        last_source = "unknown"

        # 尝试 axdata
        if sp in ("any", "", "axdata_only") and axdata_cfg:
            ok, data, source = self._call_source("axdata", axdata_cfg, **params)
            if ok and data:
                pid = infer_provider_from_name(axdata_cfg["interface"]) or "axdata"
                return RouteResult(success=True, data=data, provider=pid, source=source)
            if not ok:
                last_error = data[0].get("error", "未知错误") if data else "未知错误"
                last_source = source

        # 尝试 akshare
        if sp in ("any", "", "akshare_only") and akshare_cfg:
            ok, data, source = self._call_source("akshare", akshare_cfg, **params)
            if ok and data:
                pid = infer_provider_from_name(akshare_cfg["func"]) or "akshare"
                return RouteResult(success=True, data=data, provider=pid, source=source)
            if not ok:
                last_error = data[0].get("error", "未知错误") if data else "未知错误"
                last_source = source

        if last_error:
            return RouteResult(success=False, data=[], source=last_source, error=last_error)
        return RouteResult(success=True, data=[], source=last_source)

    @staticmethod
    def _call_source(source_type: str, cfg: dict, **params) -> tuple[bool, list[dict], str]:
        """调用指定类型的数据源。"""
        if source_type == "axdata":
            from core.registry import _call_axdata
            return _call_axdata(cfg, **params)
        elif source_type == "akshare":
            from core.registry import _call_akshare
            return _call_akshare(cfg, **params)
        return False, [], "unknown"

    def list_routes(self) -> dict[str, dict]:
        """列出所有路由配置。"""
        result = {}
        for interface, cfg in self.sources_config.items():
            providers = self.get_interface_providers(interface)
            axdata_iface = cfg.get("axdata", {}).get("interface") if cfg.get("axdata") else None
            akshare_func = cfg.get("akshare", {}).get("func") if cfg.get("akshare") else None
            result[interface] = {
                "description": cfg.get("desc", ""),
                "providers": providers,
                "axdata": axdata_iface,
                "akshare": akshare_func,
            }
        return result

    def list_by_provider(self, provider_id: str) -> dict[str, dict]:
        """按 provider 列出所有接口。"""
        result = {}
        for interface, cfg in self.sources_config.items():
            providers = self.get_interface_providers(interface)
            if provider_id.lower() in providers:
                axdata_iface = cfg.get("axdata", {}).get("interface") if cfg.get("axdata") else None
                akshare_func = cfg.get("akshare", {}).get("func") if cfg.get("akshare") else None
                result[interface] = {
                    "description": cfg.get("desc", ""),
                    "axdata": axdata_iface,
                    "akshare": akshare_func,
                }
        return result
