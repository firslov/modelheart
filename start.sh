#!/bin/bash

WORKERS=${WORKERS:-$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)}
PORT=${PORT:-8087}
HOST=${HOST:-0.0.0.0}
LOG_LEVEL=${LOG_LEVEL:-warning}

# 加载环境变量
[ -f .env ] && export $(grep -v '^#' .env | xargs)

# 开发模式
if [ "$DEV" = "1" ]; then
    echo "Starting in DEV mode..."
    uvicorn app.main:app --host "$HOST" --port "$PORT" --reload --log-level "$LOG_LEVEL"
    exit 0
fi

# 生产模式
echo "Starting in PROD mode with $WORKERS workers..."

if command -v gunicorn &> /dev/null; then
    gunicorn app.main:app \
        --workers "$WORKERS" \
        --worker-class uvicorn.workers.UvicornWorker \
        --bind "$HOST:$PORT" \
        --timeout 300 \
        --keep-alive 30 \
        --max-requests 10000 \
        --max-requests-jitter 1000 \
        --access-logfile - \
        --log-level "$LOG_LEVEL" \
        --worker-connections 1000 2>&1 | grep -v "Handling signal: winch"
else
    uvicorn app.main:app \
        --host "$HOST" \
        --port "$PORT" \
        --workers "$WORKERS" \
        --log-level "$LOG_LEVEL" \
        --loop uvloop \
        --http httptools
fi
