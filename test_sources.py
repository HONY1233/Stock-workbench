#!/usr/bin/env python3
"""测试按来源分类和按需调用的功能。"""
import json
import sys

# 模拟 MCP 环境，直接导入函数测试
from core.registry import SourceRegistry
from core.tool_providers import (
    list_all_providers,
    list_tools_by_provider,
    get_tool_providers,
)


def test_registry_providers():
    """测试 SourceRegistry 的 provider 相关方法。"""
    registry = SourceRegistry()

    print("=== 测试 get_providers ===")
    providers = registry.get_providers()
    print(f"YAML 配置中的所有 providers: {sorted(providers)}")
    assert "sina" in providers
    assert "eastmoney" in providers
    assert "cls" in providers
    print("OK\n")

    print("=== 测试 list_by_provider ===")
    sina_tools = registry.list_by_provider("sina")
    print(f"sina 提供的接口数: {len(sina_tools)}")
    assert "stock_daily" in sina_tools
    assert "index_daily" in sina_tools
    print(f"sina 接口示例: {list(sina_tools.keys())[:5]}")
    print("OK\n")

    cls_tools = registry.list_by_provider("cls")
    print(f"cls 提供的接口数: {len(cls_tools)}")
    assert "cls_telegraph" in cls_tools
    print(f"cls 接口: {list(cls_tools.keys())}")
    print("OK\n")

    print("=== 测试 get_source_providers ===")
    providers = registry.get_source_providers("stock_daily")
    print(f"stock_daily 的 providers: {providers}")
    assert "tencent" in providers
    assert "sina" in providers
    print("OK\n")


def test_tool_providers():
    """测试自定义工具的 provider 映射。"""
    print("=== 测试自定义工具 provider 映射 ===")
    providers = list_all_providers()
    print(f"自定义工具涉及的所有 providers: {sorted(providers)}")
    assert "sina" in providers
    assert "eastmoney" in providers
    assert "cls" in providers
    print("OK\n")

    print("=== 测试 list_tools_by_provider ===")
    sina_tools = list_tools_by_provider("sina")
    print(f"sina 的自定义工具数: {len(sina_tools)}")
    assert "stock_zh_a_daily" in sina_tools
    assert "stock_zh_a_spot" in sina_tools
    print(f"sina 自定义工具: {sina_tools}")
    print("OK\n")

    cls_tools = list_tools_by_provider("cls")
    print(f"cls 的自定义工具数: {len(cls_tools)}")
    assert "cls_telegraph" in cls_tools
    print("OK\n")

    print("=== 测试 get_tool_providers ===")
    providers = get_tool_providers("tencent_realtime_quote")
    print(f"tencent_realtime_quote 的 providers: {providers}")
    assert "tencent" in providers
    print("OK\n")


def test_call_unified_source_preference():
    """测试 call_unified 的 source_preference 参数。"""
    from core.registry import call_unified

    registry = SourceRegistry()

    print("=== 测试 source_preference='any' ===")
    # 这个测试可能会因为网络问题失败，但我们主要测试参数传递和逻辑
    ok, data, source = call_unified("index_daily", registry.sources, source_preference="any")
    print(f"any 模式: ok={ok}, source={source}")
    # 至少不应该因为参数问题报错
    print("OK\n")

    print("=== 测试 source_preference='akshare_only' ===")
    ok, data, source = call_unified("index_daily", registry.sources, source_preference="akshare_only")
    print(f"akshare_only 模式: ok={ok}, source={source}")
    print("OK\n")

    print("=== 测试 source_preference='axdata_only'（接口无 axdata） ===")
    ok, data, source = call_unified("index_daily", registry.sources, source_preference="axdata_only")
    print(f"axdata_only 模式（无axdata）: ok={ok}, source={source}")
    # 应该返回空或失败，但不会崩溃
    print("OK\n")

    print("=== 测试 source_preference='sina' ===")
    ok, data, source = call_unified("stock_daily", registry.sources, source_preference="sina")
    print(f"provider='sina' 模式: ok={ok}, source={source}")
    print("OK\n")

    print("=== 测试 source_preference='不存在的provider' ===")
    ok, data, source = call_unified("stock_daily", registry.sources, source_preference="nonexist")
    print(f"不存在的 provider: ok={ok}, error={data[0].get('error') if data else '无错误'}")
    assert not ok
    print("OK\n")


def test_yaml_providers_field():
    """测试 YAML 中是否正确加载了 providers 字段。"""
    registry = SourceRegistry()

    print("=== 测试 YAML providers 字段 ===")
    cfg = registry.get_source("stock_daily")
    assert cfg is not None
    assert "providers" in cfg
    assert cfg["providers"] == ["tencent", "sina"]
    print(f"stock_daily providers: {cfg['providers']}")
    print("OK\n")

    cfg = registry.get_source("global_news_em")
    assert cfg["providers"] == ["eastmoney"]
    print(f"global_news_em providers: {cfg['providers']}")
    print("OK\n")


if __name__ == "__main__":
    try:
        test_yaml_providers_field()
        test_registry_providers()
        test_tool_providers()
        test_call_unified_source_preference()
        print("=" * 50)
        print("所有测试通过！")
        sys.exit(0)
    except AssertionError as e:
        print(f"测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"测试异常: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
