#!/usr/bin/env python3
"""
数据库迁移脚本 v2 - 修复模型名称字段命名问题

此脚本将：
1. 重命名 server_models 表中的字段，使其更清晰：
   - client_model_name -> backend_model_name (实际后端模型名称)
   - actual_model_name -> frontend_model_name (前端使用的模型名称)
2. 清理 api_keys 表中的冗余时间字段（可选，需要谨慎处理）

注意：此迁移需要谨慎执行，确保不影响现有功能。
"""

import asyncio
import sys
import os
import sqlite3
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.database import engine
from app.database.models import Base
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def check_table_exists(session: AsyncSession, table_name: str) -> bool:
    """检查表是否存在"""
    result = await session.execute(
        text(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
    )
    return result.scalar() is not None


async def check_column_exists(session: AsyncSession, table_name: str, column_name: str) -> bool:
    """检查列是否存在"""
    result = await session.execute(
        text(f"PRAGMA table_info({table_name})")
    )
    columns = result.fetchall()
    return any(col[1] == column_name for col in columns)


async def migrate_server_models_table(session: AsyncSession):
    """迁移 server_models 表，重命名字段"""
    print("检查 server_models 表结构...")
    
    # 检查表是否存在
    if not await check_table_exists(session, "server_models"):
        print("server_models 表不存在，跳过迁移")
        return
    
    # 检查是否需要迁移（检查新字段是否已存在）
    if await check_column_exists(session, "server_models", "backend_model_name"):
        print("backend_model_name 字段已存在，可能已经迁移过")
        return
    
    print("开始迁移 server_models 表...")
    
    try:
        # 1. 添加新字段
        await session.execute(
            text("ALTER TABLE server_models ADD COLUMN backend_model_name VARCHAR(100)")
        )
        await session.execute(
            text("ALTER TABLE server_models ADD COLUMN frontend_model_name VARCHAR(100)")
        )
        print("已添加新字段")
        
        # 2. 复制数据：将 client_model_name 复制到 backend_model_name
        #    将 actual_model_name 复制到 frontend_model_name
        await session.execute(
            text("""
            UPDATE server_models 
            SET backend_model_name = client_model_name,
                frontend_model_name = actual_model_name
            """)
        )
        print("已复制数据到新字段")
        
        # 3. 删除旧字段（可选，先注释掉以确保安全）
        # await session.execute(text("ALTER TABLE server_models DROP COLUMN client_model_name"))
        # await session.execute(text("ALTER TABLE server_models DROP COLUMN actual_model_name"))
        # print("已删除旧字段")
        
        # 4. 更新唯一约束
        await session.execute(
            text("DROP INDEX IF EXISTS uq_server_model")
        )
        await session.execute(
            text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_server_model_new 
            ON server_models (server_id, frontend_model_name)
            """)
        )
        print("已更新唯一约束")
        
        await session.commit()
        print("server_models 表迁移完成！")
        
    except Exception as e:
        await session.rollback()
        print(f"迁移 server_models 表时出错: {e}")
        raise


async def cleanup_redundant_time_fields(session: AsyncSession):
    """清理冗余的时间字段（可选）"""
    print("检查冗余时间字段...")
    
    if not await check_table_exists(session, "api_keys"):
        print("api_keys 表不存在，跳过清理")
        return
    
    # 检查冗余字段是否存在
    has_created_at_str = await check_column_exists(session, "api_keys", "created_at_str")
    has_last_used_str = await check_column_exists(session, "api_keys", "last_used_str")
    
    if not has_created_at_str and not has_last_used_str:
        print("冗余时间字段不存在，跳过清理")
        return
    
    print("注意：清理冗余时间字段是破坏性操作，需要谨慎处理")
    print("当前跳过此步骤，仅记录建议")
    
    # 建议方案：
    # 1. 确保所有代码都使用 DateTime 字段
    # 2. 在 to_dict() 方法中统一格式化
    # 3. 然后可以安全地删除 String 字段
    
    # 示例代码（注释掉）：
    # if has_created_at_str:
    #     # 确保 created_at_str 数据已同步到 created_at
    #     await session.execute(text("""
    #     UPDATE api_keys 
    #     SET created_at = datetime(created_at_str)
    #     WHERE created_at_str IS NOT NULL AND created_at_str != ''
    #     """))
    #     
    #     # 然后删除字段
    #     # await session.execute(text("ALTER TABLE api_keys DROP COLUMN created_at_str"))
    # 
    # if has_last_used_str:
    #     # 类似处理 last_used_str
    #     # await session.execute(text("ALTER TABLE api_keys DROP COLUMN last_used_str"))
    pass


async def update_password_hash_length(session: AsyncSession):
    """更新 password_hash 字段长度以支持更长的 bcrypt 哈希"""
    print("检查 password_hash 字段长度...")
    
    if not await check_table_exists(session, "api_keys"):
        print("api_keys 表不存在，跳过更新")
        return
    
    # SQLite 不支持直接修改列类型，需要创建新表
    # 这是一个复杂的操作，需要谨慎处理
    print("注意：修改字段长度在 SQLite 中需要复杂的表重建操作")
    print("当前跳过此步骤，建议在下次数据库重构时处理")
    
    # bcrypt 哈希通常为 60 字符，但某些实现可能更长
    # 当前长度为 255，通常足够，但可以增加到 512 以确保安全
    pass


async def create_backup(database_path: str):
    """创建数据库备份"""
    backup_path = database_path + ".backup"
    
    if os.path.exists(database_path):
        import shutil
        shutil.copy2(database_path, backup_path)
        print(f"已创建数据库备份: {backup_path}")
    else:
        print(f"数据库文件不存在: {database_path}")


async def main():
    """主函数"""
    print("开始数据库迁移 v2...")
    
    # 获取数据库路径
    from app.config.settings import settings
    import os
    
    database_path = os.path.join(settings.BASE_DIR, 'app', 'database', 'myapi.db')
    print(f"数据库路径: {database_path}")
    
    # 创建备份
    await create_backup(database_path)
    
    # 创建异步会话
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    async with async_session() as session:
        try:
            # 执行迁移步骤
            await migrate_server_models_table(session)
            await cleanup_redundant_time_fields(session)
            await update_password_hash_length(session)
            
            print("\n迁移完成！")
            print("重要提示：")
            print("1. 迁移添加了新字段但保留了旧字段，确保向后兼容")
            print("2. 需要更新代码以使用新字段名称")
            print("3. 测试所有功能确保正常工作后，可以删除旧字段")
            
        except Exception as e:
            print(f"迁移过程中发生错误: {e}")
            import traceback
            traceback.print_exc()
            print("\n已回滚所有更改")
            print("请检查错误并重试")


if __name__ == "__main__":
    asyncio.run(main())
