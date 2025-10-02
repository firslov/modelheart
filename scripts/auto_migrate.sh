#!/bin/bash
# 云服务器数据一键迁移脚本

set -e  # 遇到错误立即退出

echo "=========================================="
echo "    MyAPI 数据迁移工具"
echo "=========================================="

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查必要文件
check_requirements() {
    log_info "检查环境要求..."
    
    # 检查Python
    if ! command -v python &> /dev/null; then
        log_error "Python未安装"
        exit 1
    fi
    
    # 检查必要文件
    if [ ! -f "api_keys_usage.json" ]; then
        log_error "api_keys_usage.json 文件不存在"
        exit 1
    fi
    
    if [ ! -f "llm_servers_list.json" ]; then
        log_error "llm_servers_list.json 文件不存在"
        exit 1
    fi
    
    if [ ! -f "requirements.txt" ]; then
        log_error "requirements.txt 文件不存在"
        exit 1
    fi
    
    log_info "环境检查通过"
}

# 备份数据
backup_data() {
    log_info "备份现有数据..."
    
    local backup_dir="backup_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$backup_dir"
    
    # 备份数据库文件
    if [ -d "app/database" ]; then
        cp -r app/database/ "$backup_dir/" 2>/dev/null || true
    fi
    
    # 备份JSON文件
    cp api_keys_usage.json "$backup_dir/" 2>/dev/null || true
    cp llm_servers_list.json "$backup_dir/" 2>/dev/null || true
    
    log_info "数据已备份到: $backup_dir"
}

# 停止服务
stop_service() {
    log_info "停止运行中的服务..."
    
    # 尝试多种方式停止服务
    pkill -f "python app/main.py" 2>/dev/null || true
    sleep 2
    
    # 检查是否还有进程在运行
    if pgrep -f "python app/main.py" > /dev/null; then
        log_warn "强制停止服务..."
        pkill -9 -f "python app/main.py" 2>/dev/null || true
    fi
    
    log_info "服务已停止"
}

# 清理旧数据库
clean_old_database() {
    log_info "清理旧数据库文件..."
    
    rm -f app/database/*.db 2>/dev/null || true
    rm -f myapi.db 2>/dev/null || true
    
    log_info "旧数据库文件已清理"
}

# 初始化数据库
init_database() {
    log_info "初始化数据库表结构..."
    
    if ! python scripts/init_database.py; then
        log_error "数据库初始化失败"
        exit 1
    fi
    
    log_info "数据库表结构创建成功"
}

# 验证数据库结构
verify_database() {
    log_info "验证数据库结构..."
    
    if ! command -v sqlite3 &> /dev/null; then
        log_warn "sqlite3 未安装，跳过数据库验证"
        return 0
    fi
    
    local tables=$(sqlite3 app/database/myapi.db ".tables" 2>/dev/null || echo "")
    
    if [[ $tables == *"api_keys"* ]] && [[ $tables == *"llm_servers"* ]]; then
        log_info "数据库表结构验证通过"
    else
        log_error "数据库表结构验证失败"
        exit 1
    fi
}

# 迁移API密钥数据
migrate_api_keys() {
    log_info "迁移API密钥数据..."
    
    if ! python scripts/migrate_api_keys.py; then
        log_error "API密钥数据迁移失败"
        exit 1
    fi
    
    log_info "API密钥数据迁移完成"
}

# 迁移LLM服务器数据
migrate_llm_servers() {
    log_info "迁移LLM服务器数据..."
    
    if ! python scripts/migrate_llm_servers.py; then
        log_error "LLM服务器数据迁移失败"
        exit 1
    fi
    
    log_info "LLM服务器数据迁移完成"
}

# 验证数据完整性
verify_data() {
    log_info "验证数据完整性..."
    
    if ! command -v sqlite3 &> /dev/null; then
        log_warn "sqlite3 未安装，跳过数据验证"
        return 0
    fi
    
    local api_keys_count=$(sqlite3 app/database/myapi.db "SELECT COUNT(*) FROM api_keys;" 2>/dev/null || echo "0")
    local llm_servers_count=$(sqlite3 app/database/myapi.db "SELECT COUNT(*) FROM llm_servers;" 2>/dev/null || echo "0")
    local server_models_count=$(sqlite3 app/database/myapi.db "SELECT COUNT(*) FROM server_models;" 2>/dev/null || echo "0")
    
    log_info "API密钥数量: $api_keys_count"
    log_info "LLM服务器数量: $llm_servers_count"
    log_info "服务器模型数量: $server_models_count"
    
    if [ "$api_keys_count" -eq 0 ] || [ "$llm_servers_count" -eq 0 ]; then
        log_error "数据迁移不完整"
        exit 1
    fi
    
    log_info "数据完整性验证通过"
}

# 启动服务
start_service() {
    log_info "启动应用程序..."
    
    # 后台启动应用
    nohup PYTHONPATH=. python app/main.py > app.log 2>&1 &
    
    # 等待应用启动
    sleep 5
    
    # 检查应用是否启动成功
    if ! pgrep -f "python app/main.py" > /dev/null; then
        log_error "应用启动失败，请检查日志: tail -f app.log"
        exit 1
    fi
    
    log_info "应用程序已启动"
}

# 测试应用
test_application() {
    log_info "测试应用程序..."
    
    # 等待应用完全启动
    sleep 3
    
    # 测试根路径
    if curl -s http://localhost:8087/ > /dev/null; then
        log_info "应用程序测试通过"
    else
        log_warn "应用程序测试失败，但进程仍在运行"
    fi
}

# 主函数
main() {
    log_info "开始数据迁移流程..."
    
    # 执行迁移步骤
    check_requirements
    backup_data
    stop_service
    clean_old_database
    init_database
    verify_database
    migrate_api_keys
    migrate_llm_servers
    verify_data
    start_service
    test_application
    
    echo ""
    log_info "=========================================="
    log_info "    数据迁移完成！"
    log_info "=========================================="
    log_info "应用运行在: http://localhost:8087"
    log_info "查看日志: tail -f app.log"
    log_info "停止应用: pkill -f 'python app/main.py'"
    echo ""
}

# 执行主函数
main "$@"
