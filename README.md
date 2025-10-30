# MyAPI - LLM API 中转服务

轻量化的LLM API请求中转系统，支持多模型接入和用量管理。

## 🚀 核心功能

- **多模型支持** - 统一接入多种LLM模型，自动负载均衡
- **API密钥管理** - 基于手机号的密钥生成和安全认证
- **用量监控** - 实时统计、限额管理和使用分析
- **流式响应** - 支持流式对话，提升用户体验
- **管理面板** - 可视化仪表板，便于管理和监控

## 🛠️ 快速开始

### 环境要求
- Python 3.8+
- SQLite数据库

### 安装运行
```bash
# 安装依赖
pip install -r requirements.txt

# 初始化数据库
python scripts/init_database.py

# 启动服务
python -m app.main
```

服务启动后访问：http://localhost:8087

### 生产部署
```bash
# 使用systemd服务
sudo cp scripts/myapi.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable myapi
sudo systemctl start myapi
```

## 📁 项目结构

```
myapi/
├── app/                    # 应用核心
│   ├── api/               # API路由
│   ├── config/            # 配置管理
│   ├── core/              # 核心逻辑
│   ├── database/          # 数据库操作
│   ├── middleware/        # 中间件
│   ├── models/            # 数据模型
│   ├── services/          # 业务服务
│   └── utils/             # 工具函数
├── scripts/               # 脚本文件
├── static/                # 静态资源
├── templates/             # HTML模板
└── requirements.txt       # 依赖列表
```

## 🔌 API接口

### 管理接口
- `GET /` - 首页，生成API密钥
- `GET /get-usage` - 用量统计和管理面板
- `GET /models` - 获取可用模型列表
- `POST /generate-api-key` - 生成API密钥

### LLM接口
- `POST /v1/chat/completions` - 聊天补全（兼容OpenAI）
- `POST /v1/completions` - 文本补全
- `POST /v1/embeddings` - 文本向量化
- `POST /anthropic/v1/messages` - Anthropic API转发

## ⚙️ 配置说明

### 环境变量
```bash
export SESSION_SECRET_KEY="your-secret-key"
export DEFAULT_LIMIT=1000000
```

### 数据库配置
项目使用SQLite数据库，所有配置数据存储在数据库中，无需JSON文件。

## 📊 功能特性

### 用量管理
- 基于token的精确用量计算
- 模型权重配置支持
- 实时限额检查和统计

### 安全认证
- API密钥验证
- 手机号+密码双重认证
- 会话管理和权限控制

### 多模型支持
- 统一API接口
- 自动负载均衡
- 服务器健康检查

## 🔧 开发说明

### 添加新模型
1. 通过管理面板添加服务器配置
2. 配置模型映射和权重
3. 启用模型状态

### 自定义配置
修改 `app/config/settings.py` 中的配置项。

## 📖 详细文档

- [快速启动指南](scripts/QUICK_START.md) - 详细的部署和运维说明

## 📄 许可证

MIT License
