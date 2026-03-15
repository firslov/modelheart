# 使用官方 Python 基础镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir gunicorn

# 复制入口脚本
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# 复制应用代码
COPY . .

# 创建必要的目录
RUN mkdir -p logs app/database

# 暴露端口
EXPOSE 8087

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV ENV=production
ENV PORT=8087
ENV HOST=0.0.0.0

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["gunicorn", "app.main:app", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8087", "--workers", "4", "--timeout", "300", "--keep-alive", "30", "--max-requests", "10000", "--max-requests-jitter", "1000", "--access-logfile", "-", "--log-level", "warning"]
