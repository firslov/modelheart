#!/bin/bash
# Model Heart 启动脚本

WORKERS=${WORKERS:-$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)}
PORT=${PORT:-8087}
HOST=${HOST:-0.0.0.0}
LOG_LEVEL=${LOG_LEVEL:-warning}  # 默认使用 warning，屏蔽 winch 信号日志

# 加载 .env 文件（如果存在）
if [ -f ".env" ]; then
    echo "Loading environment from .env file..."
    export $(grep -v '^#' .env | xargs)
fi

# 开发模式：单进程 + 热重载
if [ "$DEV" = "1" ]; then
    echo "Starting Model Heart (DEV mode)..."
    uvicorn app.main:app --host "$HOST" --port "$PORT" --reload --log-level "$LOG_LEVEL"
    exit 0
fi

# 生产模式：多进程
echo "Starting Model Heart (PROD mode) with $WORKERS workers..."

# 优先使用 gunicorn，回退到 uvicorn
if command -v gunicorn &> /dev/null; then
    # 使用 grep 过滤 winch 信号日志（只过滤包含 "Handling signal: winch" 的完整行）
    { gunicorn app.main:app \
        --workers "$WORKERS" \
        --worker-class uvicorn.workers.UvicornWorker \
        --bind "$HOST:$PORT" \
        --timeout 300 \
        --keep-alive 30 \
        --max-requests 10000 \
        --max-requests-jitter 1000 \
        --access-logfile - \
        --log-level "$LOG_LEVEL" \
        --worker-connections 1000 2>&1 | grep -vE "Handling signal: winch|^\\[.*\\].*Handling signal: winch"; } || true
else
    uvicorn app.main:app \
        --host "$HOST" \
        --port "$PORT" \
        --workers "$WORKERS" \
        --log-level "$LOG_LEVEL" \
        --loop uvloop \
        --http httptools
fi
