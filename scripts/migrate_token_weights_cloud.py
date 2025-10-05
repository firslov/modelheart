#!/usr/bin/env python3
"""
云端部署项目token权重迁移脚本
为现有的server_models表添加input_token_weight和output_token_weight字段
"""

import asyncio
import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.database import AsyncSessionLocal
from sqlalchemy import text


async def migrate_token_weights():
    """迁移数据库，添加token权重字段"""
    print("🚀 开始迁移数据库，添加token权重字段...")
    
    async with AsyncSessionLocal() as session:
        try:
            # 检查表是否存在
            result = await session.execute(text("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='server_models'
            """))
            table_exists = result.fetchone()
            
            if not table_exists:
                print("❌ server_models表不存在，请先创建数据库表结构")
                return
            
            # 检查是否已经存在input_token_weight字段
            result = await session.execute(text("""
                PRAGMA table_info(server_models)
            """))
            columns = result.fetchall()
            column_names = [col[1] for col in columns]
            
            # 添加input_token_weight字段
            if 'input_token_weight' not in column_names:
                print("📝 添加input_token_weight字段...")
                await session.execute(text("""
                    ALTER TABLE server_models 
                    ADD COLUMN input_token_weight REAL DEFAULT 1.0
                """))
                print("✅ input_token_weight字段添加成功")
            else:
                print("✅ input_token_weight字段已存在")
            
            # 添加output_token_weight字段
            if 'output_token_weight' not in column_names:
                print("📝 添加output_token_weight字段...")
                await session.execute(text("""
                    ALTER TABLE server_models 
                    ADD COLUMN output_token_weight REAL DEFAULT 1.0
                """))
                print("✅ output_token_weight字段添加成功")
            else:
                print("✅ output_token_weight字段已存在")
            
            # 提交事务
            await session.commit()
            
            # 验证迁移结果
            result = await session.execute(text("""
                SELECT COUNT(*) as model_count,
                       SUM(CASE WHEN input_token_weight IS NULL THEN 1 ELSE 0 END) as null_input_weights,
                       SUM(CASE WHEN output_token_weight IS NULL THEN 1 ELSE 0 END) as null_output_weights
                FROM server_models
            """))
            stats = result.fetchone()
            
            print(f"\n📊 迁移统计:")
            print(f"   模型总数: {stats[0]}")
            print(f"   空输入权重数: {stats[1]}")
            print(f"   空输出权重数: {stats[2]}")
            
            # 如果有空值，设置默认值
            if stats[1] > 0 or stats[2] > 0:
                print("🔄 设置默认权重值...")
                await session.execute(text("""
                    UPDATE server_models 
                    SET input_token_weight = 1.0 
                    WHERE input_token_weight IS NULL
                """))
                await session.execute(text("""
                    UPDATE server_models 
                    SET output_token_weight = 1.0 
                    WHERE output_token_weight IS NULL
                """))
                await session.commit()
                print("✅ 默认权重值设置完成")
            
            print("\n🎉 数据库迁移成功完成！")
            
        except Exception as e:
            await session.rollback()
            print(f"❌ 数据库迁移失败: {e}")
            raise


async def backup_database():
    """备份数据库（可选）"""
    import shutil
    import datetime
    
    db_path = "app/database/llm_service.db"
    if os.path.exists(db_path):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"app/database/llm_service_backup_{timestamp}.db"
        shutil.copy2(db_path, backup_path)
        print(f"📦 数据库已备份到: {backup_path}")
    else:
        print("⚠️  数据库文件不存在，跳过备份")


async def main():
    """主函数"""
    print("=" * 50)
    print("云端部署项目Token权重迁移工具")
    print("=" * 50)
    
    # 询问是否备份数据库
    backup_choice = input("是否备份数据库？(y/N): ").strip().lower()
    if backup_choice == 'y':
        await backup_database()
    
    # 执行迁移
    await migrate_token_weights()
    
    print("\n" + "=" * 50)
    print("迁移完成！")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
