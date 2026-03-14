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

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境

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

### 3. 初始化数据库

```bash
python scripts/init_database.py
```

### 4. 启动服务

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

## 🏗️ 项目结构

```
myapi/
├── app/
│   ├── api/              # API 路由
│   ├── config/           # 配置管理
│   ├── core/             # 应用核心
│   ├── database/         # 数据层
│   ├── middleware/       # 中间件
│   ├── models/           # 数据模型
│   ├── services/         # 业务逻辑
│   └── utils/            # 工具函数
├── static/               # 静态资源
├── templates/            # HTML 模板
├── scripts/              # 脚本文件
├── .env.example          # 配置模板
├── requirements.txt      # 依赖列表
└── start.sh              # 启动脚本
```

## 📄 许可证

MIT License

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

**Made with ❤️ by [firslov](https://github.com/firslov)**
