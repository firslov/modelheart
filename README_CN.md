# Model Heart - LLM API 网关

企业级 LLM API 网关系统，支持多模型聚合、智能路由和统一认证。

🌐 **在线演示**: [https://api.aihao.world](https://api.aihao.world)

[🇺🇸 English](README.md)

---

## ✨ 核心特性

- 🔄 **智能负载均衡** — 加权轮询、健康检查、熔断器、自动故障转移
- 🔐 **统一认证** — API Key 管理、手机号注册、管理员面板
- 📊 **用量监控** — Token 级计费、实时限额、分模型统计
- 🌐 **多协议支持** — OpenAI `/v1/chat/completions`、`/v1/embeddings`、`/v1/completions`，Anthropic `/v1/messages`，Coding `/chat/completions`
- 🚀 **高性能** — HTTP/2、SSE 流式、异步批量写入、多级缓存

## 🚀 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境
cp .env.example .env

# 3. 初始化数据库
python scripts/init_database.py

# 4. 启动
./start.sh
```

默认访问: http://localhost:8087

### Docker

```bash
docker-compose up -d
```

## 📖 API 接口

| 端点 | 格式 | 计费方式 |
|------|------|---------|
| `/v1/chat/completions` | OpenAI | 按 Token |
| `/v1/completions` | OpenAI | 按 Token |
| `/v1/embeddings` | OpenAI | 按 Token |
| `/v1/models` | OpenAI | — |
| `/anthropic/v1/messages` | Anthropic | 按请求 |
| `/coding/chat/completions` | OpenAI | 按请求 |

### OpenAI 兼容

```bash
curl https://api.your-domain.com/v1/chat/completions \
  -H "Authorization: Bearer your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o","messages":[{"role":"user","content":"你好"}]}'
```

### Anthropic 兼容

```bash
curl https://api.your-domain.com/anthropic/v1/messages \
  -H "x-api-key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-sonnet-4-20250514","max_tokens":1024,"messages":[{"role":"user","content":"你好"}]}'
```

## 🔧 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ENV` | 运行环境 | `development` |
| `DOMAIN` | 域名 | `localhost` |
| `API_BASE_URL` | API 基础 URL | `http://localhost:8087` |
| `SESSION_SECRET_KEY` | Session 密钥 | — |
| `ADMIN_USERNAME` | 管理员用户名 | `admin` |
| `ADMIN_PASSWORD_HASH` | 管理员 bcrypt 哈希 | — |
| `DEFAULT_LIMIT` | 默认 API 限额 (tokens) | `1000000` |
| `ANTHROPIC_VERSION` | Anthropic API 版本 | `2023-06-01` |

## 🏗️ 项目结构

```
├── app/
│   ├── api/              # API 路由
│   ├── config/           # 配置管理
│   ├── core/             # 应用生命周期
│   ├── database/         # 数据库模型与 Repository
│   ├── middleware/        # 认证、日志、请求体限制
│   ├── models/           # Pydantic 数据模型
│   ├── services/         # LLM 代理、API 服务、用量队列
│   └── utils/            # 熔断器、响应缓存、工具函数
├── static/               # 静态资源
├── templates/            # Jinja2 模板
├── scripts/              # 初始化脚本
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## 📄 许可证

MIT
