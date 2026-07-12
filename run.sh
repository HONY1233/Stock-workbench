#!/usr/bin/env bash
# AKShare MCP Server 启动脚本
# 用法:
#   ./run.sh                # stdio 模式（默认，供 IDE 集成）
#   ./run.sh sse            # SSE 模式，0.0.0.0:8000
#   ./run.sh sse 9000       # SSE 模式，0.0.0.0:9000
#   ./run.sh http 8080      # streamable-http 模式，0.0.0.0:8080
#   ./run.sh list           # 列出所有可用工具

set -e
cd "$(dirname "$0")"

MODE="${1:-stdio}"
PORT="${2:-8000}"
HOST="0.0.0.0"

# 确认 Python 环境
if ! command -v python3 &>/dev/null; then
    echo "错误: 未找到 python3"
    exit 1
fi

# 检查依赖
python3 -c "import fastmcp, akshare, pandas, axdata" 2>/dev/null || {
    echo "正在安装依赖..."
    pip install -r requirements.txt
}

case "$MODE" in
    stdio)
        echo "启动 AKShare MCP Server (stdio 模式)..."
        exec python3 server.py --transport stdio
        ;;
    sse)
        echo "启动 AKShare MCP Server (SSE 模式) - http://${HOST}:${PORT}/sse"
        exec python3 server.py --transport sse --host "$HOST" --port "$PORT"
        ;;
    http)
        echo "启动 AKShare MCP Server (streamable-http 模式) - http://${HOST}:${PORT}/mcp"
        exec python3 server.py --transport streamable-http --host "$HOST" --port "$PORT"
        ;;
    list)
        exec python3 server.py --list
        ;;
    *)
        echo "用法: $0 [stdio|sse|http|list] [port]"
        echo "  stdio  - 标准输入输出模式（默认）"
        echo "  sse    - SSE 模式，端口默认 8000"
        echo "  http   - streamable-http 模式，端口默认 8000"
        echo "  list   - 列出所有可用工具"
        exit 1
        ;;
esac
