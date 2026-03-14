# Model Heart - LLM API Gateway

![Model Heart](static/index.jpeg)

An enterprise-grade LLM API gateway system supporting multi-model aggregation, intelligent routing, and unified authentication.

🌐 **Live Demo**: [https://api.aihao.world](https://api.aihao.world)

[🇨🇳 中文文档](README_CN.md)

---

## ✨ Core Features

- 🔄 **Intelligent Load Balancing** - Weighted round-robin, health checks, automatic failover
- 🔐 **Unified Authentication** - API Key management, Session control, permission management
- 📊 **Usage Monitoring** - Token-level statistics, real-time quotas, multi-dimensional analysis
- 🌐 **Multi-Protocol Support** - OpenAI / Anthropic compatible interfaces
- 🚀 **High Performance** - HTTP/2 support, streaming response, connection pool optimization

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Copy configuration template
cp .env.example .env

# Edit configuration file
vim .env
```

**Required Configuration**:

```bash
# Domain configuration
DOMAIN=your-domain.com
API_BASE_URL=https://api.your-domain.com

# Session secret key (must be changed to a random string)
SESSION_SECRET_KEY=your-random-secret-key

# Admin password (generate hash)
# Generate with: python -c "import bcrypt; print(bcrypt.hashpw(b'your_password', bcrypt.gensalt()).decode())"
ADMIN_PASSWORD_HASH=$2b$12$...
```

### 3. Initialize Database

```bash
python scripts/init_database.py
```

### 4. Start Service

```bash
# Production
./start.sh

# Development (auto-reload)
DEV=1 ./start.sh

# Custom parameters
WORKERS=8 PORT=9000 LOG_LEVEL=debug ./start.sh
```

Visit: http://localhost:8087

## 📖 API Usage

### 📊 Billing

Usage is charged based on tokens consumed. The billing method varies by endpoint:

| Endpoint | Billing Method | Details |
|----------|----------------|---------|
| `/v1/chat/completions` | Token-based | Input tokens × Input weight + Output tokens × Output weight |
| `/v1/completions` | Token-based | Input tokens × Input weight + Output tokens × Output weight |
| `/v1/embeddings` | Token-based | Input tokens × Model weight |
| `/anthropic/v1/messages` | Request-based | Max(Input weight, Output weight) × Request count |
| `/coding/chat/completions` | Request-based | Max(Input weight, Output weight) × Request count |

### OpenAI Compatible Interface

#### Chat Completions - `/v1/chat/completions`
- **Billing**: Token-based (input + output tokens)
- **Use Case**: General chat applications

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
- **Billing**: Token-based (input tokens only)
- **Use Case**: Text embedding and similarity search

```bash
curl https://api.your-domain.com/v1/embeddings \
  -H "Authorization: Bearer your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "text-embedding-ada-002",
    "input": "Hello world"
  }'
```

#### Coding Interface - `/coding/chat/completions`
- **Billing**: Request-based (max of input/output weights)
- **Use Case**: Code generation, Zhipu AI Coding Plan, etc.
- **Note**: OpenAI-compatible format but charged per request

```bash
curl https://api.your-domain.com/coding/chat/completions \
  -H "Authorization: Bearer your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "zhipu-coding-model",
    "messages": [{"role": "user", "content": "Write a Python function"}]
  }'
```

### Anthropic Compatible Interface

#### Messages - `/anthropic/v1/messages`
- **Billing**: Request-based (max of input/output weights)
- **Use Case**: Claude models and request-based billing models

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

## 🔧 Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ENV` | Runtime environment | `development` |
| `DOMAIN` | Domain name | `localhost` |
| `API_BASE_URL` | API base URL | `http://localhost:8087` |
| `SESSION_SECRET_KEY` | Session secret key | - |
| `ADMIN_USERNAME` | Admin username | `admin` |
| `ADMIN_PASSWORD_HASH` | Admin password hash | - |
| `DEFAULT_LIMIT` | Default API limit | `1000000` |

## 🏗️ Project Structure

```
myapi/
├── app/
│   ├── api/              # API routes
│   ├── config/           # Configuration management
│   ├── core/             # Application core
│   ├── database/         # Data layer
│   ├── middleware/       # Middleware
│   ├── models/           # Data models
│   ├── services/         # Business logic
│   └── utils/            # Utility functions
├── static/               # Static assets
├── templates/            # HTML templates
├── scripts/              # Scripts
├── .env.example          # Configuration template
├── requirements.txt      # Dependencies
└── start.sh              # Startup script
```

## 📄 License

MIT License

## 🤝 Contributing

Issues and Pull Requests are welcome!

---

**Made with ❤️ by [firslov](https://github.com/firslov)**
