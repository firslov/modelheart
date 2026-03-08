# Model Heart - LLM API 中转服务

![Model Heart](static/index.jpeg)

智能化的 LLM API 请求转发系统，支持多模型接入、负载均衡和用量管理。

🌐 **在线展示**: [https://api.aihao.world](https://api.aihao.world)

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 初始化数据库
python scripts/init_database.py

# 启动服务
./start.sh              # 生产环境
DEV=1 ./start.sh       # 开发环境
```

访问: http://localhost:8087

## 启动参数

```bash
WORKERS=8 ./start.sh        # Worker 数量
PORT=9000 ./start.sh        # 端口
LOG_LEVEL=debug ./start.sh  # 日志级别
```

## 核心功能

### 智能负载均衡
- 加权轮询算法
- 健康检查机制
- 连接池优化

### 安全认证
- 手机号+密码认证
- API 密钥管理
- Session 权限控制

### 用量监控
- Token 级统计
- 实时限额控制
- 多维度分析

### 多协议支持
- OpenAI 兼容: `/v1/chat/completions`, `/v1/completions`, `/v1/embeddings`
- Anthropic 原生: `/anthropic/v1/messages`
- SSE 流式响应

## API 接口

### 用户接口
- `GET /` - 用户注册页面
- `POST /generate-api-key` - 生成 API 密钥
- `POST /check-usage` - 查询使用额度

### 管理接口
- `GET /login` - 管理员登录
- `GET /dashboard` - 管理控制台
- `GET /models` - 获取模型列表
- `POST /update-llm-servers` - 更新服务器配置

## 配置

```bash
# 环境变量
export SESSION_SECRET_KEY="your-secret-key"
export DEFAULT_LIMIT=1000000
export ENV=production
```

## 架构

```
myapi/
├── app/              # 应用核心
│   ├── api/         # 路由层
│   ├── config/      # 配置管理
│   ├── core/        # 应用工厂
│   ├── database/    # 数据层
│   ├── middleware/  # 中间件
│   ├── models/      # 数据模型
│   ├── services/    # 业务逻辑
│   └── utils/       # 工具函数
├── scripts/         # 部署脚本
├── static/          # 静态资源
└── templates/       # HTML 模板
```

## 许可证

MIT
