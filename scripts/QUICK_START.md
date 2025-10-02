# 云服务器数据迁移快速指南

## 一键迁移（推荐）

```bash
# 1. 确保在项目根目录
cd /path/to/myapi

# 2. 执行一键迁移脚本
./scripts/auto_migrate.sh
```

## 手动分步迁移

```bash
# 1. 停止服务
pkill -f "python app/main.py"

# 2. 备份数据
cp -r app/database/ backup_$(date +%Y%m%d_%H%M%S)/

# 3. 清理旧数据库
rm -f app/database/*.db

# 4. 初始化数据库
python scripts/init_database.py

# 5. 迁移数据
python scripts/migrate_api_keys.py
python scripts/migrate_llm_servers.py

# 6. 启动服务
nohup PYTHONPATH=. python app/main.py > app.log 2>&1 &

# 7. 验证
curl http://localhost:8087/
```

## 验证迁移结果

```bash
# 检查数据库表
sqlite3 app/database/myapi.db ".tables"

# 检查数据量
sqlite3 app/database/myapi.db "
SELECT 'API密钥' as 类型, COUNT(*) as 数量 FROM api_keys
UNION ALL
SELECT 'LLM服务器', COUNT(*) FROM llm_servers
UNION ALL
SELECT '服务器模型', COUNT(*) FROM server_models;"

# 检查应用状态
curl -s http://localhost:8087/ | head -5
```

## 预期结果

- ✅ API密钥数量: 100
- ✅ LLM服务器数量: 5  
- ✅ 服务器模型数量: 13
- ✅ 应用运行在: http://localhost:8087

## 故障排除

```bash
# 查看日志
tail -f app.log

# 检查进程
pgrep -f "python app/main.py"

# 重新启动
pkill -f "python app/main.py"
nohup PYTHONPATH=. python app/main.py > app.log 2>&1 &
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

**注意**: 迁移前请确保 `api_keys_usage.json` 和 `llm_servers_list.json` 文件存在！
