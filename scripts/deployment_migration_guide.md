# 云服务器数据迁移完整流程

## 准备工作

### 1. 环境检查
```bash
# 检查Python环境
python --version
pip --version

# 检查项目依赖
pip install -r requirements.txt
```

### 2. 文件准备
确保以下文件存在于项目根目录：
- `api_keys_usage.json` - API密钥数据
- `llm_servers_list.json` - LLM服务器配置
- `requirements.txt` - Python依赖

## 完整迁移流程

### 步骤1：停止现有服务
```bash
# 停止正在运行的应用程序
pkill -f "python app/main.py"

# 或者使用systemctl（如果配置了服务）
sudo systemctl stop myapi
```

### 步骤2：备份现有数据
```bash
# 备份现有数据库文件（如果有）
cp -r app/database/ app/database_backup_$(date +%Y%m%d_%H%M%S)/

# 备份JSON数据文件
cp api_keys_usage.json api_keys_usage_backup_$(date +%Y%m%d_%H%M%S).json
cp llm_servers_list.json llm_servers_list_backup_$(date +%Y%m%d_%H%M%S).json
```

### 步骤3：清理旧数据库文件
```bash
# 删除旧的数据库文件
rm -f app/database/*.db
rm -f myapi.db  # 根目录下的旧数据库文件
```

### 步骤4：初始化新数据库
```bash
# 创建数据库表结构
python scripts/init_database.py
```

### 步骤5：验证数据库结构
```bash
# 检查表是否创建成功
sqlite3 app/database/myapi.db ".tables"

# 预期输出：
# api_keys       llm_servers    model_usage    server_models
```

### 步骤6：迁移API密钥数据
```bash
# 执行API密钥迁移
python scripts/migrate_api_keys.py

# 验证迁移结果
sqlite3 app/database/myapi.db "SELECT COUNT(*) FROM api_keys;"
# 预期输出：100
```

### 步骤7：迁移LLM服务器数据
```bash
# 执行LLM服务器迁移
python scripts/migrate_llm_servers.py

# 验证迁移结果
sqlite3 app/database/myapi.db "SELECT COUNT(*) FROM llm_servers;"
# 预期输出：5
sqlite3 app/database/myapi.db "SELECT COUNT(*) FROM server_models;"
# 预期输出：13
```

### 步骤8：验证数据完整性
```bash
# 检查所有表的数据量
sqlite3 app/database/myapi.db "
SELECT 
    'api_keys' as table_name, COUNT(*) as count FROM api_keys
UNION ALL
SELECT 
    'llm_servers', COUNT(*) FROM llm_servers
UNION ALL
SELECT 
    'server_models', COUNT(*) FROM server_models
UNION ALL
SELECT 
    'model_usage', COUNT(*) FROM model_usage;
"
```

### 步骤9：启动应用程序
```bash
# 启动应用
PYTHONPATH=. python app/main.py

# 或者使用nohup后台运行
nohup PYTHONPATH=. python app/main.py > app.log 2>&1 &

# 或者使用systemd服务（推荐生产环境）
sudo systemctl start myapi
```

### 步骤10：验证应用运行
```bash
# 检查应用是否正常响应
curl -s http://localhost:8087/ | head -5

# 检查API端点
curl -s http://localhost:8087/get-usage

# 检查日志
tail -f app.log
```

## 自动化脚本

### 创建一键迁移脚本
```bash
#!/bin/bash
# scripts/auto_migrate.sh

echo "开始数据迁移流程..."

# 停止服务
echo "1. 停止服务..."
pkill -f "python app/main.py" || true

# 备份
echo "2. 备份数据..."
backup_dir="backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p $backup_dir
cp -r app/database/ $backup_dir/ || true
cp *.json $backup_dir/ || true

# 清理旧数据库
echo "3. 清理旧数据库..."
rm -f app/database/*.db
rm -f myapi.db

# 初始化数据库
echo "4. 初始化数据库..."
python scripts/init_database.py

# 迁移数据
echo "5. 迁移API密钥数据..."
python scripts/migrate_api_keys.py

echo "6. 迁移LLM服务器数据..."
python scripts/migrate_llm_servers.py

# 验证
echo "7. 验证数据..."
sqlite3 app/database/myapi.db ".tables"

# 启动服务
echo "8. 启动服务..."
nohup PYTHONPATH=. python app/main.py > app.log 2>&1 &

echo "迁移完成！应用日志：tail -f app.log"
```

## 故障排除

### 常见问题及解决方案

1. **数据库连接错误**
   ```bash
   # 检查数据库文件权限
   ls -la app/database/
   chmod 644 app/database/myapi.db
   ```

2. **迁移脚本找不到文件**
   ```bash
   # 确保JSON文件在正确位置
   ls -la *.json
   ```

3. **表结构不匹配**
   ```bash
   # 重新初始化数据库
   rm -f app/database/myapi.db
   python scripts/init_database.py
   ```

4. **应用启动失败**
   ```bash
   # 检查日志
   tail -f app.log
   
   # 检查端口占用
   netstat -tulpn | grep 8087
   ```

## 生产环境建议

1. **使用systemd服务**
   ```ini
   # /etc/systemd/system/myapi.service
   [Unit]
   Description=MyAPI LLM Service
   After=network.target

   [Service]
   Type=simple
   User=www-data
   WorkingDirectory=/path/to/myapi
   Environment=PYTHONPATH=/path/to/myapi
   ExecStart=/usr/bin/python app/main.py
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

2. **配置日志轮转**
   ```ini
   # /etc/logrotate.d/myapi
   /path/to/myapi/app.log {
       daily
       rotate 7
       compress
       delaycompress
       missingok
       notifempty
   }
   ```

3. **数据库备份策略**
   ```bash
   # 每日备份脚本
   cp app/database/myapi.db /backup/myapi_$(date +%Y%m%d).db
   ```

## 验证清单

- [ ] 备份现有数据
- [ ] 停止运行中的服务
- [ ] 清理旧数据库文件
- [ ] 初始化新数据库结构
- [ ] 迁移API密钥数据
- [ ] 迁移LLM服务器数据
- [ ] 验证数据完整性
- [ ] 启动应用程序
- [ ] 测试功能正常
- [ ] 配置生产环境服务
