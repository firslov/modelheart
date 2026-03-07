# Model Heart - LLM API 中转服务

智能化的LLM API请求转发系统，提供多模型接入、负载均衡和完善的用量管理。

## ✨ 核心功能

### 🔄 智能负载均衡

- **加权轮询算法** - 根据服务器性能和响应时间动态分配请求
- **健康检查机制** - 自动监控服务器状态，故障秒级切换
- **连接池优化** - 动态调整连接池大小，适应不同负载场景

### 🔐 安全认证体系

- **双重认证** - 手机号+密码的用户注册认证
- **API密钥管理** - 安全的密钥生成和管理机制
- **权限控制** - 基于Session的管理员权限系统

### 📊 精准用量监控

- **Token级统计** - 支持不同模型的输入/输出Token权重配置
- **实时限额控制** - 动态检查用户使用额度
- **多维度分析** - 按用户、模型、服务器等多维度使用统计

### 🌐 多协议支持

- **OpenAI兼容** - `/v1/chat/completions`、`/v1/completions`、`/v1/embeddings`
- **Anthropic原生** - `/anthropic/v1/messages` 接口直接转发
- **流式响应** - 完整支持SSE流式传输，优化用户体验

### 🎛️ 可视化管理

- **现代化界面** - 响应式Web管理面板
- **实时监控** - 服务器状态、模型使用情况实时展示
- **便捷操作** - 一键添加/删除服务器，启用/禁用模型

## 🚀 快速开始

### 环境要求

- Python 3.8+
- SQLite（内置）

### 安装部署

```bash
# 安装依赖
pip install -r requirements.txt

# 初始化数据库
python scripts/init_database.py

# 启动服务
./start.sh                    # 生产环境（多进程）
DEV=1 ./start.sh             # 开发环境（单进程+热重载）
```

访问：**<http://localhost:8087>**

### 启动参数

```bash
WORKERS=8 ./start.sh         # 自定义 worker 数量
PORT=9000 ./start.sh         # 自定义端口
LOG_LEVEL=debug ./start.sh   # 调整日志级别
```

推荐安装高性能依赖：
```bash
pip install uvloop httptools gunicorn
```

### 生产环境

```bash
# 安装高性能依赖（推荐）
pip install uvloop httptools gunicorn

# 启动服务
./start.sh
```

## 📋 API 接口

### 用户接口
- `GET /` - 用户注册页面
- `POST /generate-api-key` - 生成API密钥
- `POST /check-usage` - 查询使用额度

### 管理接口
- `GET /login` - 管理员登录
- `GET /dashboard` - 管理控制台
- `GET /models` - 获取模型列表
- `POST /update-llm-servers` - 更新服务器配置

### LLM转发接口

| Endpoint | 请求格式 | 用量计算 | 适用场景 |
|----------|---------|---------|---------|
| `/v1/chat/completions` | OpenAI | Token × 权重 | OpenAI API |
| `/v1/completions` | OpenAI | Token × 权重 | OpenAI API |
| `/v1/embeddings` | OpenAI | Token × 权重 | OpenAI Embeddings |
| `/anthropic/v1/messages` | Anthropic | 请求数 × max(输入权重, 输出权重) | Anthropic API |
| `/coding` | OpenAI | 请求数 × max(输入权重, 输出权重) | 智谱AI、通义千问等 |

**用量计算示例：**
- OpenAI: `(输入Token × 输入权重) + (输出Token × 输出权重)`
- Anthropic/Coding: `请求数 × max(输入权重, 输出权重)`

## 🏗️ 系统架构

```
myapi/
├── app/                    # 应用核心模块
│   ├── api/               # RESTful API路由层
│   ├── config/            # 配置管理（环境变量、系统设置）
│   ├── core/              # 应用工厂和核心逻辑
│   ├── database/          # 数据库ORM和会话管理
│   ├── middleware/        # 认证和权限中间件
│   ├── models/            # 数据模型定义
│   ├── services/          # 业务逻辑层（LLM服务、API服务）
│   └── utils/             # 工具函数和辅助模块
├── scripts/               # 部署和维护脚本
├── static/                # 前端静态资源（JS/CSS/图片）
├── templates/             # Jinja2 HTML模板
└── requirements.txt       # Python依赖包列表
```

## ⚙️ 配置

### 环境变量

```bash
export SESSION_SECRET_KEY="your-secret-key-here"  # Session加密密钥（必需）
export DEFAULT_LIMIT=1000000                      # 默认用户Token限额
export ENV=production                             # 运行环境
```

### 数据库表结构

- `api_keys` - API密钥和用户信息
- `llm_servers` - LLM服务器配置
- `server_models` - 模型映射关系
- `model_usage` - 使用统计记录

## 🎯 使用场景

### 🏢 企业级应用

- **多模型统一接入** - 同时支持OpenAI、Anthropic、本地模型等
- **成本控制** - 精确的Token用量统计和限额管理
- **高可用性** - 多服务器负载均衡，故障自动切换

### 👥 个人开发者

- **简化接入** - 统一的API接口，无需适配不同平台
- **用量可视化** - 直观的使用统计和成本分析
- **灵活扩展** - 支持自定义模型和服务器配置

## 🔧 高级特性

### 智能路由算法

- **健康检查** - 定期ping服务器，自动剔除故障节点
- **权重调整** - 根据响应时间和错误率动态调整权重
- **连接复用** - HTTP/2支持，提升传输效率

### 性能优化

- **异步架构** - 全异步处理，支持高并发
- **流式传输** - SSE协议支持，实时响应体验
- **缓存机制** - 智能缓存常用配置，减少数据库查询

## 📈 监控指标

### 系统指标

- 服务器健康状态和响应时间
- API请求成功率和错误分布
- 连接池使用情况

### 业务指标

- 用户注册和使用活跃度
- 各模型使用频次和成本
- Token消耗趋势分析

## 🤝 贡献指南

欢迎提交Issue和Pull Request来改进项目！

## 📄 许可证

MIT License
