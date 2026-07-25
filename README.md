# Model Heart - LLM API Gateway

An enterprise-grade LLM API gateway supporting multi-model aggregation, intelligent routing, and unified authentication.

🌐 **Live Demo**: [https://api.aihao.world](https://api.aihao.world)

[🇨🇳 中文文档](README_CN.md)

---

## ✨ Core Features

- 🔄 **Intelligent Load Balancing** — Weighted round-robin, health checks, circuit breaker, automatic failover
- 🔐 **Unified Authentication** — API Key management, phone-based user registration, admin dashboard
- 📊 **Usage Monitoring** — Token-level billing, real-time quotas, per-model statistics
- 🌐 **Multi-Protocol** — OpenAI `/v1/chat/completions`, `/v1/embeddings`, `/v1/completions`, Anthropic `/v1/messages`, Coding `/chat/completions`
- 🚀 **High Performance** — HTTP/2, SSE streaming, async batch writes, multi-level caching

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env

# 3. Initialize database
python scripts/init_database.py

# 4. Start
./start.sh
```

Default access: http://localhost:8087

### Docker

```bash
docker-compose up -d
```

## 📖 API Endpoints

| Endpoint | Format | Billing |
|----------|--------|---------|
| `/v1/chat/completions` | OpenAI | Token-based |
| `/v1/completions` | OpenAI | Token-based |
| `/v1/embeddings` | OpenAI | Token-based |
| `/v1/models` | OpenAI | — |
| `/anthropic/v1/messages` | Anthropic | Request-based |
| `/coding/chat/completions` | OpenAI | Request-based |

### OpenAI Compatible

```bash
curl https://api.your-domain.com/v1/chat/completions \
  -H "Authorization: Bearer your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o","messages":[{"role":"user","content":"Hello"}]}'
```

### Anthropic Compatible

```bash
curl https://api.your-domain.com/anthropic/v1/messages \
  -H "x-api-key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-sonnet-4-20250514","max_tokens":1024,"messages":[{"role":"user","content":"Hello"}]}'
```

## 🔧 Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ENV` | Runtime environment | `development` |
| `DOMAIN` | Domain name | `localhost` |
| `API_BASE_URL` | API base URL | `http://localhost:8087` |
| `SESSION_SECRET_KEY` | Session secret | — |
| `ADMIN_USERNAME` | Admin username | `admin` |
| `ADMIN_PASSWORD_HASH` | Admin bcrypt hash | — |
| `DEFAULT_LIMIT` | Default API quota (tokens) | `1000000` |
| `ANTHROPIC_VERSION` | Anthropic API version | `2023-06-01` |

## 🏗️ Project Structure

```
├── app/
│   ├── api/              # API routes
│   ├── config/           # Settings
│   ├── core/             # Application lifecycle
│   ├── database/         # SQLAlchemy models & repositories
│   ├── middleware/        # Auth, logging, body limit
│   ├── models/           # Pydantic schemas
│   ├── services/         # LLM proxy, API service, usage queue
│   └── utils/            # Circuit breaker, response cache, helpers
├── static/               # Static assets
├── templates/            # Jinja2 templates
├── scripts/              # DB init scripts
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## 📄 License

MIT
