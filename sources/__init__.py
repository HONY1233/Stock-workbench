"""自定义源模块包。

每个模块实现 register(mcp) -> list[str] 函数，返回注册的工具名列表。
server.py 启动时自动扫描并加载所有模块。
"""
