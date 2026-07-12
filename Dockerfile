FROM python:3.12-slim

LABEL maintainer="HONY1233 <1747608470@qq.com>"
LABEL description="AKShare + AxData MCP Server - 金融数据 MCP 服务器"

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# 先复制依赖文件，利用 Docker 缓存层
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY server.py .
COPY cls_telegraph.py .
COPY run.sh .
COPY mcp.json .
COPY README.md .

RUN chmod +x run.sh

# 默认环境变量
ENV MCP_TRANSPORT=sse
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8000

EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${MCP_PORT}/sse', timeout=3)" || exit 1

# 默认启动 SSE 服务
CMD ["sh", "-c", "python server.py -t ${MCP_TRANSPORT} --host ${MCP_HOST} --port ${MCP_PORT}"]
