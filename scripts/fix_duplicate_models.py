#!/usr/bin/env python3
"""
修复server_models表中的重复数据问题
添加唯一约束并清理重复数据
"""

import os
import sys
import sqlite3
from pathlib import Path
import asyncio

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.database.database import DATABASE_URL


class DatabaseFixer:
    """数据库修复器"""
    
    def __init__(self, db_path=None):
        self.db_path = db_path or DATABASE_URL.replace("sqlite+aiosqlite:///", "")
        self.sync_db_path = self.db_path
        self.changes_made = []
        
    async def fix_all(self):
        """执行所有修复"""
        print("=" * 80)
        print("数据库修复开始")
        print("=" * 80)
        
        # 备份数据库
        await self.backup_database()
        
        # 检查并修复重复数据
        await self.fix_duplicate_models()
        
        # 添加唯一约束
        await self.add_unique_constraint()
        
        # 输出修复报告
        self.print_report()
        
    async def backup_database(self):
        """备份数据库"""
        import shutil
        import time
        
        backup_path = f"{self.sync_db_path}.backup.{int(time.time())}"
        
        try:
            shutil.copy2(self.sync_db_path, backup_path)
            print(f"📁 数据库已备份到: {backup_path}")
            self.changes_made.append(f"创建备份: {backup_path}")
            return True
        except Exception as e:
            print(f"❌ 备份数据库失败: {e}")
            return False
    
    async def fix_duplicate_models(self):
        """修复server_models表中的重复数据"""
        print("\n1. 检查并修复重复数据...")
        
        try:
            conn = sqlite3.connect(self.sync_db_path)
            cursor = conn.cursor()
            
            # 1. 查找重复数据
            cursor.execute("""
                SELECT server_id, actual_model_name, COUNT(*) as count, 
                       GROUP_CONCAT(id) as ids
                FROM server_models 
                GROUP BY server_id, actual_model_name 
                HAVING count > 1
            """)
            duplicates = cursor.fetchall()
            
            if not duplicates:
                print("  ✅ 没有发现重复数据")
                conn.close()
                return True
            
            print(f"  🔍 发现 {len(duplicates)} 组重复数据")
            
            # 2. 处理每组重复数据
            total_deleted = 0
            for server_id, actual_model_name, count, ids_str in duplicates:
                ids = [int(id) for id in ids_str.split(',')]
                print(f"  📊 服务器 {server_id}, 模型 {actual_model_name}: {count} 条重复记录 (IDs: {ids})")
                
                # 保留第一条记录（最小的id），删除其他重复记录
                keep_id = min(ids)
                delete_ids = [id for id in ids if id != keep_id]
                
                # 合并请求计数
                cursor.execute("""
                    SELECT SUM(reqs) as total_reqs 
                    FROM server_models 
                    WHERE id IN ({})
                """.format(','.join(map(str, ids))))
                total_reqs = cursor.fetchone()[0] or 0
                
                # 更新保留记录的请求计数
                cursor.execute("""
                    UPDATE server_models 
                    SET reqs = ? 
                    WHERE id = ?
                """, (total_reqs, keep_id))
                
                # 删除重复记录
                cursor.execute("""
                    DELETE FROM server_models 
                    WHERE id IN ({})
                """.format(','.join(map(str, delete_ids))))
                
                deleted_count = len(delete_ids)
                total_deleted += deleted_count
                
                print(f"    ✅ 保留 ID {keep_id} (reqs={total_reqs}), 删除 {deleted_count} 条重复记录")
                self.changes_made.append(
                    f"清理重复: 服务器 {server_id}, 模型 {actual_model_name} - 保留 ID {keep_id}, 删除 {deleted_count} 条记录"
                )
            
            # 3. 提交更改
            conn.commit()
            conn.close()
            
            print(f"  ✅ 共删除 {total_deleted} 条重复记录")
            return True
            
        except Exception as e:
            print(f"  ❌ 修复重复数据时出错: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def add_unique_constraint(self):
        """为server_models表添加唯一约束"""
        print("\n2. 添加唯一约束...")
        
        try:
            conn = sqlite3.connect(self.sync_db_path)
            cursor = conn.cursor()
            
            # 检查是否已存在唯一约束
            cursor.execute("PRAGMA index_list(server_models)")
            indexes = cursor.fetchall()
            
            # 查找是否已有唯一索引
            has_unique_constraint = False
            for index in indexes:
                idx_name = index[1]
                if idx_name.startswith('sqlite_autoindex_server_models_'):
                    has_unique_constraint = True
                    break
            
            if has_unique_constraint:
                print("  ✅ 唯一约束已存在")
                conn.close()
                return True
            
            # 由于SQLite的ALTER TABLE不支持直接添加UNIQUE约束，
            # 我们需要创建一个新表并迁移数据
            
            print("  ⚙️  创建新表并迁移数据...")
            
            # 1. 创建临时表
            cursor.execute("""
                CREATE TABLE server_models_new (
                    id INTEGER NOT NULL,
                    server_id INTEGER NOT NULL,
                    client_model_name VARCHAR(100) NOT NULL,
                    actual_model_name VARCHAR(100) NOT NULL,
                    reqs INTEGER,
                    status BOOLEAN,
                    input_token_weight FLOAT,
                    output_token_weight FLOAT,
                    PRIMARY KEY (id),
                    UNIQUE (server_id, actual_model_name),
                    FOREIGN KEY(server_id) REFERENCES llm_servers (id) ON DELETE CASCADE
                )
            """)
            
            # 2. 迁移数据（使用INSERT OR IGNORE避免重复）
            cursor.execute("""
                INSERT OR IGNORE INTO server_models_new 
                (id, server_id, client_model_name, actual_model_name, reqs, status, input_token_weight, output_token_weight)
                SELECT id, server_id, client_model_name, actual_model_name, reqs, status, input_token_weight, output_token_weight
                FROM server_models
                ORDER BY id
            """)
            
            migrated_count = cursor.rowcount
            print(f"  📊 迁移了 {migrated_count} 条记录")
            
            # 3. 删除旧表
            cursor.execute("DROP TABLE server_models")
            
            # 4. 重命名新表
            cursor.execute("ALTER TABLE server_models_new RENAME TO server_models")
            
            # 5. 重新创建索引
            cursor.execute("CREATE INDEX ix_server_models_server_id ON server_models(server_id)")
            
            # 6. 提交更改
            conn.commit()
            conn.close()
            
            print("  ✅ 唯一约束添加成功")
            self.changes_made.append("添加唯一约束: (server_id, actual_model_name)")
            return True
            
        except Exception as e:
            print(f"  ❌ 添加唯一约束时出错: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def print_report(self):
        """打印修复报告"""
        print("\n" + "=" * 80)
        print("修复报告")
        print("=" * 80)
        
        if not self.changes_made:
            print("✅ 没有需要修复的问题")
            return
        
        print(f"📋 执行的修复操作 ({len(self.changes_made)} 项):")
        for i, change in enumerate(self.changes_made, 1):
            print(f"  {i}. {change}")
        
        print("\n✅ 修复完成！")
        print("=" * 80)
    
    async def verify_fix(self):
        """验证修复结果"""
        print("\n" + "=" * 80)
        print("验证修复结果")
        print("=" * 80)
        
        try:
            conn = sqlite3.connect(self.sync_db_path)
            cursor = conn.cursor()
            
            # 1. 检查是否还有重复数据
            cursor.execute("""
                SELECT server_id, actual_model_name, COUNT(*) as count
                FROM server_models 
                GROUP BY server_id, actual_model_name 
                HAVING count > 1
            """)
            duplicates = cursor.fetchall()
            
            if duplicates:
                print(f"❌ 仍然发现 {len(duplicates)} 组重复数据:")
                for server_id, actual_model_name, count in duplicates:
                    print(f"  服务器 {server_id}, 模型 {actual_model_name}: {count} 条记录")
            else:
                print("✅ 没有重复数据")
            
            # 2. 检查唯一约束
            cursor.execute("PRAGMA index_list(server_models)")
            indexes = cursor.fetchall()
            
            has_unique_constraint = False
            for index in indexes:
                idx_name = index[1]
                if idx_name.startswith('sqlite_autoindex_server_models_'):
                    has_unique_constraint = True
                    break
            
            if has_unique_constraint:
                print("✅ 唯一约束已生效")
            else:
                print("❌ 唯一约束未找到")
            
            # 3. 检查数据完整性
            cursor.execute("SELECT COUNT(*) FROM server_models")
            count = cursor.fetchone()[0]
            print(f"📊 server_models表现有记录: {count} 条")
            
            conn.close()
            
            if not duplicates and has_unique_constraint:
                print("\n🎉 所有验证通过！")
                return True
            else:
                print("\n⚠️  验证未完全通过，请检查问题")
                return False
                
        except Exception as e:
            print(f"❌ 验证时出错: {e}")
            return False


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="修复server_models表重复数据问题")
    parser.add_argument("--db", help="数据库文件路径", default=None)
    parser.add_argument("--dry-run", help="只检查不修改", action="store_true")
    parser.add_argument("--verify", help="只验证不修复", action="store_true")
    
    args = parser.parse_args()
    
    fixer = DatabaseFixer(args.db)
    
    if args.verify:
        await fixer.verify_fix()
    elif args.dry_run:
        print("🔍 干运行模式（只检查不修改）")
        # 这里可以添加只检查的逻辑
        await fixer.verify_fix()
    else:
        await fixer.fix_all()
        print("\n" + "=" * 80)
        print("验证修复结果...")
        print("=" * 80)
        await fixer.verify_fix()


if __name__ == "__main__":
    asyncio.run(main())
