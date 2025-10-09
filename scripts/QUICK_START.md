# 快速启动指南

## 初始化数据库

```bash
# 1. 确保在项目根目录
cd /path/to/myapi

# 2. 初始化数据库
python scripts/init_database.py
```

## 启动服务

```bash
# 启动服务
nohup PYTHONPATH=. python app/main.py > app.log 2>&1 &

# 或者直接运行
PYTHONPATH=. python app/main.py
```

## 验证服务

```bash
# 检查应用状态
curl http://localhost:8087/

# 查看日志
tail -f app.log

# 检查进程
pgrep -f "python app/main.py"
```

## 数据库管理

```bash
# 检查数据库表
sqlite3 database.db ".tables"

# 检查数据量
sqlite3 database.db "
SELECT 'API密钥' as 类型, COUNT(*) as 数量 FROM api_keys
UNION ALL
SELECT 'LLM服务器', COUNT(*) FROM llm_servers
UNION ALL
SELECT '服务器模型', COUNT(*) FROM server_models;"
```

## 生产环境建议

```bash
# 使用systemd服务（推荐）
sudo cp scripts/myapi.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable myapi
sudo systemctl start myapi
```

---

**注意**: 项目现在使用SQLite数据库存储所有配置数据，不再依赖JSON文件。
