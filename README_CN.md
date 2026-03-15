# Model Heart - LLM API 网关

![Model Heart](static/index.jpeg)

企业级 LLM API 网关系统，支持多模型聚合、智能路由和统一认证。

🌐 **在线演示**: [https://api.aihao.world](https://api.aihao.world)

[🇺🇸 English](README.md)

---

## ✨ 核心特性

- 🔄 **智能负载均衡** - 加权轮询、健康检查、自动故障转移
- 🔐 **统一认证** - API Key 管理、Session 控制、权限管理
- 📊 **用量监控** - Token 级统计、实时限额、多维度分析
- 🌐 **多协议支持** - OpenAI / Anthropic 兼容接口
- 🚀 **高性能** - HTTP/2 支持、流式响应、连接池优化

## 🚀 快速部署

### 方案一：Docker 部署（推荐）

使用 Docker Compose 一键部署，最简单快捷：

```bash
# 1. 克隆仓库
git clone <repository-url>
cd myapi

# 2. 配置环境
cp .env.example .env
# 编辑 .env 文件，配置必要参数

# 3. 启动服务
docker-compose up -d

# 4. 查看日志
docker-compose logs -f
```

**默认访问地址**: http://localhost:8087

**默认管理员账号**:
- 用户名: `admin`
- 密码: `admin`（如果未设置 ADMIN_PASSWORD_HASH）

> ⚠️ **重要**: 首次登录后请立即修改默认密码！

#### Docker Compose 常用命令

```bash
# 启动服务
docker-compose up -d

# 停止服务
docker-compose down

# 重启服务
docker-compose restart

# 查看日志
docker-compose logs -f

# 更新到最新版本
docker-compose pull && docker-compose up -d

# 使用 Nginx 反向代理
docker-compose --profile with-nginx up -d
```

### 方案二：手动部署

#### 1. 安装依赖

```bash
pip install -r requirements.txt
```

#### 2. 配置环境

```bash
# 复制配置模板
cp .env.example .env

# 编辑配置文件
vim .env
```

**必需配置项**:

```bash
# 域名配置
DOMAIN=your-domain.com
API_BASE_URL=https://api.your-domain.com

# Session 密钥（必须修改为随机字符串）
SESSION_SECRET_KEY=your-random-secret-key

# 管理员密码（生成哈希）
# 生成方式: python -c "import bcrypt; print(bcrypt.hashpw(b'your_password', bcrypt.gensalt()).decode())"
ADMIN_PASSWORD_HASH=$2b$12$...
```

#### 3. 初始化数据库

```bash
python scripts/init_database.py
```

#### 4. 启动服务

```bash
# 生产环境
./start.sh

# 开发环境（自动重载）
DEV=1 ./start.sh

# 自定义参数
WORKERS=8 PORT=9000 LOG_LEVEL=debug ./start.sh
```

访问: http://localhost:8087

## 📖 API 使用

### 📊 计费方式

用量根据消耗的 Token 数计费，不同端点的计费方式不同：

| 端点 | 计费方式 | 详细说明 |
|------|----------|----------|
| `/v1/chat/completions` | 按 Token 计费 | 输入 Token × 输入权重 + 输出 Token × 输出权重 |
| `/v1/completions` | 按 Token 计费 | 输入 Token × 输入权重 + 输出 Token × 输出权重 |
| `/v1/embeddings` | 按 Token 计费 | 输入 Token × 模型权重 |
| `/anthropic/v1/messages` | 按请求计费 | Max(输入权重, 输出权重) × 请求次数 |
| `/coding/chat/completions` | 按请求计费 | Max(输入权重, 输出权重) × 请求次数 |

### OpenAI 兼容接口

#### Chat Completions - `/v1/chat/completions`
- **计费**: 按 Token 计费（输入 + 输出）
- **适用场景**: 通用对话应用

```bash
curl https://api.your-domain.com/v1/chat/completions \
  -H "Authorization: Bearer your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-3.5-turbo",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

#### Embeddings - `/v1/embeddings`
- **计费**: 按 Token 计费（仅输入）
- **适用场景**: 文本嵌入和相似度搜索

```bash
curl https://api.your-domain.com/v1/embeddings \
  -H "Authorization: Bearer your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "text-embedding-ada-002",
    "input": "Hello world"
  }'
```

#### Coding 接口 - `/coding/chat/completions`
- **计费**: 按请求计费（输入/输出权重的最大值）
- **适用场景**: 代码生成、智谱 AI Coding Plan 等
- **说明**: OpenAI 兼容格式，但按请求计费

```bash
curl https://api.your-domain.com/coding/chat/completions \
  -H "Authorization: Bearer your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "zhipu-coding-model",
    "messages": [{"role": "user", "content": "编写一个 Python 函数"}]
  }'
```

### Anthropic 兼容接口

#### Messages - `/anthropic/v1/messages`
- **计费**: 按请求计费（输入/输出权重的最大值）
- **适用场景**: Claude 模型和按请求计费的其他模型

```bash
curl https://api.your-domain.com/anthropic/v1/messages \
  -H "x-api-key: your-api-key" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-3-5-sonnet-20241022",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

## 🔧 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ENV` | 运行环境 | `development` |
| `DOMAIN` | 域名 | `localhost` |
| `API_BASE_URL` | API 基础 URL | `http://localhost:8087` |
| `SESSION_SECRET_KEY` | Session 密钥 | - |
| `ADMIN_USERNAME` | 管理员用户名 | `admin` |
| `ADMIN_PASSWORD_HASH` | 管理员密码哈希 | - |
| `DEFAULT_LIMIT` | 默认 API 限额 | `1000000` |

## 🐳 Docker 部署指南

### 生产环境部署

1. **准备环境配置**
   ```bash
   cp .env.example .env
   # 编辑 .env 配置生产环境参数
   ```

2. **生成安全密码**
   ```bash
   # 使用 Docker 生成 bcrypt 哈希密码
   docker run --rm python:3.11-slim python -c "
   import bcrypt
   password = 'your-secure-password'
   hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
   print(hashed.decode())
   "
   ```

3. **配置 .env**
   ```bash
   DOMAIN=your-domain.com
   API_BASE_URL=https://api.your-domain.com
   SESSION_SECRET_KEY=$(openssl rand -hex 32)
   ADMIN_PASSWORD_HASH=<生成的哈希值>
   ```

4. **部署**
   ```bash
   docker-compose up -d
   ```

### 使用 Nginx 反向代理

```bash
# 创建 ssl 目录
mkdir -p ssl

# 放置 SSL 证书
# ssl/cert.pem
# ssl/key.pem

# 使用 Nginx 启动
docker-compose --profile with-nginx up -d
```

### Docker 构建（自定义）

```bash
# 构建镜像
docker build -t model-heart:latest .

# 运行容器
docker run -d \
  --name model-heart \
  -p 8087:8087 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/.env:/app/.env:ro \
  --restart unless-stopped \
  model-heart:latest
```

## 🏗️ 项目结构

```
myapi/
├── app/                    # 主应用目录
│   ├── api/                # API 路由
│   ├── config/             # 配置管理
│   ├── core/               # 应用核心
│   ├── database/           # 数据层
│   ├── middleware/         # 中间件
│   ├── models/             # 数据模型
│   ├── services/           # 业务逻辑
│   └── utils/              # 工具函数
├── static/                 # 静态资源
├── templates/              # HTML 模板
├── scripts/                # 脚本文件
├── .env.example            # 配置模板
├── requirements.txt        # 依赖列表
├── start.sh                # 启动脚本
├── Dockerfile              # Docker 镜像定义
├── docker-compose.yml      # Docker Compose 配置
├── docker-entrypoint.sh    # Docker 入口脚本
└── nginx.conf              # Nginx 配置
```

## 📄 许可证

MIT License

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

**Made with ❤️ by [firslov](https://github.com/firslov)**
