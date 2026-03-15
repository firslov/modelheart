#!/bin/bash
set -e

# 检查环境变量
if [ -z "$SESSION_SECRET_KEY" ]; then
    echo "⚠️  WARNING: SESSION_SECRET_KEY not set, generating random key..."
    export SESSION_SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
    echo "Generated SESSION_SECRET_KEY: $SESSION_SECRET_KEY"
fi

if [ -z "$ADMIN_PASSWORD_HASH" ]; then
    echo "⚠️  WARNING: ADMIN_PASSWORD_HASH not set, using default password 'admin'"
    # 默认密码 'admin' 的 bcrypt 哈希值
    export ADMIN_PASSWORD_HASH='$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewKyNiAYMyzJ/I1e'
    echo "Please change the default password after first login!"
fi

# 初始化数据库
echo "📦 Initializing database..."
python scripts/init_database.py

echo "✅ Database initialized successfully!"

# 执行传入的命令
exec "$@"
