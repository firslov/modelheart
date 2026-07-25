#!/bin/bash
set -e

# 检查环境变量
if [ -z "$SESSION_SECRET_KEY" ]; then
    echo "⚠️  WARNING: SESSION_SECRET_KEY not set, generating random key..."
    export SESSION_SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
    echo "已生成随机 SESSION_SECRET_KEY（仅本次容器生命周期有效）"
fi

if [ -z "$ADMIN_PASSWORD_HASH" ]; then
    echo "⚠️  WARNING: ADMIN_PASSWORD_HASH not set, using default password 'admin'"
    echo "⚠️  默认密码为 admin，存在安全风险，请尽快登录后修改密码！"
    # 运行时生成默认密码 'admin' 的 bcrypt 哈希值
    export ADMIN_PASSWORD_HASH=$(python -c "import bcrypt; print(bcrypt.hashpw(b'admin', bcrypt.gensalt()).decode())")
    echo "Please change the default password after first login!"
fi

# 初始化数据库
echo "📦 Initializing database..."
python scripts/init_database.py

echo "✅ Database initialized successfully!"

# 执行传入的命令
exec "$@"
