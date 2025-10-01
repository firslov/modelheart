# API Service

轻量化的LLM API请求中转系统，支持多模型接入和用量管理。

## 核心功能

- 🚀 多LLM模型统一接入
- 🔑 基于手机号的API密钥管理  
- 📊 实时用量统计和限制
- 💬 支持流式对话响应
- 🌐 配套对话网站：[https://chat.aihao.world/](https://chat.aihao.world/)

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 运行服务
python -m app.main
```

服务将在 <http://localhost:8087> 启动

## 性能测试

`scripts/llm_benchmark.py` 提供了LLM API的性能测试工具，可以测量延迟和吞吐量。

### 测试方法

1. 安装额外依赖 (如果尚未安装):

```bash
pip install httpx
```

2. 运行基准测试:

```bash
python scripts/llm_benchmark.py \
  --base-url http://your-api-server \
  --api-key your-api-key \
  --model your-model-name
```

3. 可选参数:

- `--latency-requests`: 延迟测试请求数 (默认: 10)
- `--throughput-requests`: 吞吐量测试总请求数 (默认: 100)
- `--concurrency`: 吞吐量测试并发数 (默认: 10)
- `--timeout`: 请求超时时间(秒) (默认: 30)
- `--connect-timeout`: 连接超时时间(秒) (默认: 10)

### 结果解读

- **延迟测试**: 测量连续请求的平均/最小/最大响应时间
- **吞吐量测试**: 测量并发请求的处理能力(请求数/秒)

测试完成后会输出类似结果:

```
=== Running Latency Test ===
Average latency: 0.4523s
Min latency: 0.4011s  
Max latency: 0.5214s

=== Running Throughput Test ===  
Requests per second: 23.45
Successful requests: 98/100
Time elapsed: 4.18s
```

## API接口

### 管理接口

- `GET /` - 首页，生成API密钥
- `GET /get-usage` - 用量统计和管理面板
- `GET /models` - 获取可用模型列表

### LLM接口

- `POST /v1/chat/completions` - 聊天补全（兼容OpenAI格式）
- `POST /v1/completions` - 文本补全
- `POST /v1/embeddings` - 文本向量化

## 配置说明

### API密钥配置 (api_keys_usage.json)

```json
{
  "api-key": {
    "usage": 0,
    "limit": 1000000,
    "reqs": 0,
    "created_at": "2024-02-04 12:00:00",
    "phone": "139xxxxxxxx"
  }
}
```

### 模型服务器配置 (llm_servers_list.json)

```json
{
  "server-url": {
    "model": {
      "model-name": {
        "name": "actual-model-name",
        "status": true
      }
    }
  }
}
```
