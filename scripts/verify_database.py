#!/usr/bin/env python3
"""
数据库验证脚本
用于验证数据库结构是否符合模型定义，并提供修复功能
"""

import os
import sys
import sqlite3
from pathlib import Path
import asyncio

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from app.database.database import DATABASE_URL
except ImportError:
    DATABASE_URL = "sqlite+aiosqlite:///app/database/myapi.db"


class DatabaseVerifier:
    """数据库验证器"""
    
    def __init__(self, db_path=None):
        self.db_path = db_path or DATABASE_URL.replace("sqlite+aiosqlite:///", "")
        self.sync_db_path = self.db_path
        self.issues = []
        self.fixes_applied = []
        
    async def verify_all(self):
        """执行所有验证"""
        print("=" * 80)
        print("数据库验证开始")
        print("=" * 80)
        
        # 检查数据库文件是否存在
        await self.verify_database_file()
        
        # 检查表结构
        await self.verify_tables()
        
        # 检查列定义
        await self.verify_columns()
        
        # 检查外键约束
        await self.verify_foreign_keys()
        
        # 检查索引
        await self.verify_indexes()
        
        # 检查数据完整性
        await self.verify_data_integrity()
        
        # 输出验证结果
        self.print_report()
        
    async def verify_database_file(self):
        """验证数据库文件"""
        print("\n1. 验证数据库文件...")
        
        if not os.path.exists(self.sync_db_path):
            self.issues.append({
                "level": "CRITICAL",
                "table": "N/A",
                "issue": f"数据库文件不存在: {self.sync_db_path}",
                "fix": "创建新的数据库文件"
            })
            print(f"  ❌ 数据库文件不存在: {self.sync_db_path}")
            return False
        
        file_size = os.path.getsize(self.sync_db_path)
        print(f"  ✓ 数据库文件存在: {self.sync_db_path} ({file_size} 字节)")
        
        # 尝试连接数据库
        try:
            conn = sqlite3.connect(self.sync_db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT sqlite_version()")
            version = cursor.fetchone()[0]
            conn.close()
            print(f"  ✓ SQLite版本: {version}")
            return True
        except Exception as e:
            self.issues.append({
                "level": "CRITICAL",
                "table": "N/A",
                "issue": f"无法连接数据库: {str(e)}",
                "fix": "检查数据库文件是否损坏"
            })
            print(f"  ❌ 无法连接数据库: {str(e)}")
            return False
    
    async def verify_tables(self):
        """验证表是否存在"""
        print("\n2. 验证表结构...")
        
        expected_tables = {
            "api_keys": "API密钥表",
            "model_usage": "模型使用统计表",
            "llm_servers": "LLM服务器配置表",
            "server_models": "服务器模型映射表"
        }
        
        try:
            conn = sqlite3.connect(self.sync_db_path)
            cursor = conn.cursor()
            
            # 获取现有表
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            existing_tables = {row[0] for row in cursor.fetchall()}
            
            # 检查缺失的表
            for table, description in expected_tables.items():
                if table in existing_tables:
                    print(f"  ✓ 表存在: {table} ({description})")
                else:
                    self.issues.append({
                        "level": "ERROR",
                        "table": table,
                        "issue": f"表不存在: {table}",
                        "fix": f"创建表 {table}"
                    })
                    print(f"  ❌ 表缺失: {table} ({description})")
            
            # 检查多余的表
            for table in existing_tables:
                if table not in expected_tables:
                    self.issues.append({
                        "level": "WARNING",
                        "table": table,
                        "issue": f"多余的表: {table}",
                        "fix": f"删除表 {table} (如果不需要)"
                    })
                    print(f"  ⚠️  多余的表: {table}")
            
            conn.close()
            
        except Exception as e:
            self.issues.append({
                "level": "ERROR",
                "table": "N/A",
                "issue": f"验证表结构时出错: {str(e)}",
                "fix": "检查数据库连接"
            })
            print(f"  ❌ 验证表结构时出错: {str(e)}")
    
    async def verify_columns(self):
        """验证列定义"""
        print("\n3. 验证列定义...")
        
        # 预期的列定义（从models.py中提取）
        expected_columns = {
            "api_keys": [
                ("id", "INTEGER", "NOT NULL"),
                ("api_key", "VARCHAR(64)", "NOT NULL"),
                ("usage", "FLOAT", ""),
                ("limit_value", "FLOAT", ""),
                ("reqs", "INTEGER", ""),
                ("created_at", "DATETIME", ""),
                ("last_used", "DATETIME", ""),
                ("phone", "VARCHAR(20)", ""),
                ("password_hash", "VARCHAR(255)", ""),
                ("created_at_str", "VARCHAR(20)", ""),
                ("last_used_str", "VARCHAR(20)", "")
            ],
            "model_usage": [
                ("id", "INTEGER", "NOT NULL"),
                ("api_key_id", "INTEGER", "NOT NULL"),
                ("model_name", "VARCHAR(100)", "NOT NULL"),
                ("requests", "INTEGER", ""),
                ("tokens", "FLOAT", "")
            ],
            "llm_servers": [
                ("id", "INTEGER", "NOT NULL"),
                ("server_url", "VARCHAR(255)", "NOT NULL"),
                ("device", "VARCHAR(100)", ""),
                ("apikey", "TEXT", "")
            ],
            "server_models": [
                ("id", "INTEGER", "NOT NULL"),
                ("server_id", "INTEGER", "NOT NULL"),
                ("client_model_name", "VARCHAR(100)", "NOT NULL"),
                ("actual_model_name", "VARCHAR(100)", "NOT NULL"),
                ("reqs", "INTEGER", ""),
                ("status", "BOOLEAN", ""),
                ("input_token_weight", "FLOAT", ""),
                ("output_token_weight", "FLOAT", "")
            ]
        }
        
        try:
            conn = sqlite3.connect(self.sync_db_path)
            cursor = conn.cursor()
            
            for table, expected_cols in expected_columns.items():
                # 检查表是否存在
                cursor.execute(f"PRAGMA table_info({table})")
                existing_columns = cursor.fetchall()
                
                if not existing_columns:
                    continue  # 表不存在，已在表验证中报告
                
                existing_col_names = {col[1] for col in existing_columns}
                expected_col_names = {col[0] for col in expected_cols}
                
                # 检查缺失的列
                for col_name, col_type, col_constraint in expected_cols:
                    if col_name not in existing_col_names:
                        self.issues.append({
                            "level": "ERROR",
                            "table": table,
                            "issue": f"列缺失: {table}.{col_name}",
                            "fix": f"添加列 {col_name} {col_type} {col_constraint} 到表 {table}"
                        })
                        print(f"  ❌ 列缺失: {table}.{col_name}")
                    else:
                        # 验证列类型（简化验证）
                        for col_info in existing_columns:
                            if col_info[1] == col_name:
                                actual_type = col_info[2].upper()
                                expected_type = col_type.upper()
                                
                                # SQLite类型比较（宽松）
                                if not self._type_compatible(actual_type, expected_type):
                                    self.issues.append({
                                        "level": "WARNING",
                                        "table": table,
                                        "issue": f"列类型不匹配: {table}.{col_name} (实际: {actual_type}, 预期: {expected_type})",
                                        "fix": f"修改列类型: ALTER TABLE {table} MODIFY COLUMN {col_name} {col_type}"
                                    })
                                    print(f"  ⚠️  列类型不匹配: {table}.{col_name} (实际: {actual_type}, 预期: {expected_type})")
                                break
                
                # 检查多余的列
                for col_info in existing_columns:
                    col_name = col_info[1]
                    if col_name not in expected_col_names and col_name != "id":
                        self.issues.append({
                            "level": "WARNING",
                            "table": table,
                            "issue": f"多余的列: {table}.{col_name}",
                            "fix": f"删除列 {col_name} (如果不需要)"
                        })
                        print(f"  ⚠️  多余的列: {table}.{col_name}")
            
            conn.close()
            
        except Exception as e:
            self.issues.append({
                "level": "ERROR",
                "table": "N/A",
                "issue": f"验证列定义时出错: {str(e)}",
                "fix": "检查数据库连接"
            })
            print(f"  ❌ 验证列定义时出错: {str(e)}")
    
    def _type_compatible(self, actual_type, expected_type):
        """检查类型是否兼容（SQLite类型系统较宽松）"""
        type_mapping = {
            "INTEGER": ["INT", "INTEGER", "BIGINT"],
            "VARCHAR": ["VARCHAR", "TEXT", "STRING"],
            "FLOAT": ["FLOAT", "REAL", "DOUBLE"],
            "DATETIME": ["DATETIME", "TIMESTAMP", "DATE"],
            "BOOLEAN": ["BOOLEAN", "INT", "INTEGER"],
            "TEXT": ["TEXT", "VARCHAR", "STRING"]
        }
        
        # 提取基础类型
        actual_base = actual_type.split('(')[0] if '(' in actual_type else actual_type
        expected_base = expected_type.split('(')[0] if '(' in expected_type else expected_type
        
        # 检查兼容性
        if expected_base in type_mapping:
            return actual_base in type_mapping[expected_base]
        
        return actual_base == expected_base
    
    async def verify_foreign_keys(self):
        """验证外键约束"""
        print("\n4. 验证外键约束...")
        
        expected_foreign_keys = {
            "model_usage": [
                ("api_key_id", "api_keys", "id", "CASCADE")
            ],
            "server_models": [
                ("server_id", "llm_servers", "id", "CASCADE")
            ]
        }
        
        try:
            conn = sqlite3.connect(self.sync_db_path)
            cursor = conn.cursor()
            
            # 启用外键检查
            cursor.execute("PRAGMA foreign_keys = ON")
            
            for table, expected_fks in expected_foreign_keys.items():
                cursor.execute(f"PRAGMA foreign_key_list({table})")
                existing_fks = cursor.fetchall()
                
                for fk in expected_fks:
                    local_col, ref_table, ref_col, on_delete = fk
                    
                    # 检查外键是否存在
                    fk_exists = False
                    for existing_fk in existing_fks:
                        if (existing_fk[3] == local_col and 
                            existing_fk[2] == ref_table and
                            existing_fk[4] == ref_col):
                            fk_exists = True
                            break
                    
                    if fk_exists:
                        print(f"  ✓ 外键存在: {table}.{local_col} -> {ref_table}.{ref_col}")
                    else:
                        self.issues.append({
                            "level": "ERROR",
                            "table": table,
                            "issue": f"外键缺失: {table}.{local_col} -> {ref_table}.{ref_col}",
                            "fix": f"添加外键约束: ALTER TABLE {table} ADD FOREIGN KEY ({local_col}) REFERENCES {ref_table}({ref_col}) ON DELETE {on_delete}"
                        })
                        print(f"  ❌ 外键缺失: {table}.{local_col} -> {ref_table}.{ref_col}")
            
            # 测试外键约束
            print("  ⚙️  测试外键约束...")
            try:
                cursor.execute("INSERT INTO model_usage (api_key_id, model_name) VALUES (999999, 'test')")
                conn.rollback()
                self.issues.append({
                    "level": "WARNING",
                    "table": "model_usage",
                    "issue": "外键约束未生效（插入了不存在的api_key_id）",
                    "fix": "启用外键约束: PRAGMA foreign_keys = ON"
                })
                print(f"  ⚠️  外键约束未生效")
            except sqlite3.IntegrityError:
                print(f"  ✓ 外键约束生效")
            
            conn.close()
            
        except Exception as e:
            self.issues.append({
                "level": "ERROR",
                "table": "N/A",
                "issue": f"验证外键约束时出错: {str(e)}",
                "fix": "检查数据库连接"
            })
            print(f"  ❌ 验证外键约束时出错: {str(e)}")
    
    async def verify_indexes(self):
        """验证索引"""
        print("\n5. 验证索引...")
        
        expected_indexes = {
            "api_keys": ["ix_api_keys_api_key"],
            "llm_servers": ["ix_llm_servers_server_url"]
        }
        
        try:
            conn = sqlite3.connect(self.sync_db_path)
            cursor = conn.cursor()
            
            for table, expected_idx_list in expected_indexes.items():
                cursor.execute(f"PRAGMA index_list({table})")
                existing_indexes = cursor.fetchall()
                existing_idx_names = {idx[1] for idx in existing_indexes if not idx[1].startswith('sqlite_')}
                
                for idx_name in expected_idx_list:
                    if idx_name in existing_idx_names:
                        print(f"  ✓ 索引存在: {idx_name} 在表 {table}")
                    else:
                        self.issues.append({
                            "level": "WARNING",
                            "table": table,
                            "issue": f"索引缺失: {idx_name} 在表 {table}",
                            "fix": f"创建索引: CREATE INDEX {idx_name} ON {table}({idx_name.replace('ix_'+table+'_', '')})"
                        })
                        print(f"  ⚠️  索引缺失: {idx_name} 在表 {table}")
            
            conn.close()
            
        except Exception as e:
            self.issues.append({
                "level": "ERROR",
                "table": "N/A",
                "issue": f"验证索引时出错: {str(e)}",
                "fix": "检查数据库连接"
            })
            print(f"  ❌ 验证索引时出错: {str(e)}")
    
    async def verify_data_integrity(self):
        """验证数据完整性"""
        print("\n6. 验证数据完整性...")
        
        try:
            conn = sqlite3.connect(self.sync_db_path)
            cursor = conn.cursor()
            
            # 检查表数据
            tables_to_check = ["api_keys", "model_usage", "llm_servers", "server_models"]
            
            for table in tables_to_check:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"  📊 {table}: {count} 条记录")
                
                # 检查是否有无效的外键引用
                if table == "model_usage":
                    cursor.execute("""
                        SELECT COUNT(*) FROM model_usage mu
                        LEFT JOIN api_keys ak ON mu.api_key_id = ak.id
                        WHERE ak.id IS NULL
                    """)
                    orphaned = cursor.fetchone()[0]
                    if orphaned > 0:
                        self.issues.append({
                            "level": "ERROR",
                            "table": table,
                            "issue": f"发现 {orphaned} 条孤儿记录（引用了不存在的api_key）",
                            "fix": f"删除无效记录: DELETE FROM model_usage WHERE api_key_id NOT IN (SELECT id FROM api_keys)"
                        })
                        print(f"  ❌ 发现 {orphaned} 条孤儿记录")
                
                if table == "server_models":
                    cursor.execute("""
                        SELECT COUNT(*) FROM server_models sm
                        LEFT JOIN llm_servers ls ON sm.server_id = ls.id
                        WHERE ls.id IS NULL
                    """)
                    orphaned = cursor.fetchone()[0]
                    if orphaned > 0:
                        self.issues.append({
                            "level": "ERROR",
                            "table": table,
                            "issue": f"发现 {orphaned} 条孤儿记录（引用了不存在的服务器）",
                            "fix": f"删除无效记录: DELETE FROM server_models WHERE server_id NOT IN (SELECT id FROM llm_servers)"
                        })
                        print(f"  ❌ 发现 {orphaned} 条孤儿记录")
            
            conn.close()
            
        except Exception as e:
            self.issues.append({
                "level": "ERROR",
                "table": "N/A",
                "issue": f"验证数据完整性时出错: {str(e)}",
                "fix": "检查数据库连接"
            })
            print(f"  ❌ 验证数据完整性时出错: {str(e)}")
    
    def print_report(self):
        """打印验证报告"""
        print("\n" + "=" * 80)
        print("验证报告")
        print("=" * 80)
        
        # 按级别分组问题
        critical_issues = [issue for issue in self.issues if issue["level"] == "CRITICAL"]
        error_issues = [issue for issue in self.issues if issue["level"] == "ERROR"]
        warning_issues = [issue for issue in self.issues if issue["level"] == "WARNING"]
        
        # 打印摘要
        print(f"\n📊 问题摘要:")
        print(f"  🔴 CRITICAL: {len(critical_issues)} 个")
        print(f"  ❌ ERROR: {len(error_issues)} 个")
        print(f"  ⚠️  WARNING: {len(warning_issues)} 个")
        print(f"  📋 总计: {len(self.issues)} 个问题")
        
        # 打印CRITICAL问题
        if critical_issues:
            print(f"\n🔴 CRITICAL 问题:")
            for i, issue in enumerate(critical_issues, 1):
                print(f"  {i}. [{issue['table']}] {issue['issue']}")
                print(f"     修复建议: {issue['fix']}")
        
        # 打印ERROR问题
        if error_issues:
            print(f"\n❌ ERROR 问题:")
            for i, issue in enumerate(error_issues, 1):
                print(f"  {i}. [{issue['table']}] {issue['issue']}")
                print(f"     修复建议: {issue['fix']}")
        
        # 打印WARNING问题
        if warning_issues:
            print(f"\n⚠️  WARNING 问题:")
            for i, issue in enumerate(warning_issues, 1):
                print(f"  {i}. [{issue['table']}] {issue['issue']}")
                print(f"     修复建议: {issue['fix']}")
        
        # 总结
        if not self.issues:
            print(f"\n✅ 恭喜！数据库验证通过，没有发现问题。")
        else:
            print(f"\n📝 修复建议:")
            print(f"  1. 按照上述建议修复问题")
            print(f"  2. 重新运行验证脚本确认修复")
            print(f"  3. 对于复杂问题，建议备份数据库后再操作")
        
        # 提供修复功能
        if self.issues:
            print(f"\n🛠️  自动修复功能:")
            print(f"  运行以下命令尝试自动修复:")
            print(f"    python scripts/fix_database.py")
        
        print("\n" + "=" * 80)
        print("验证完成")
        print("=" * 80)
        
    async def apply_fixes(self):
        """应用修复（需要用户确认）"""
        print("\n" + "=" * 80)
        print("应用修复")
        print("=" * 80)
        
        if not self.issues:
            print("✅ 没有需要修复的问题")
            return
        
        print(f"⚠️  警告：以下 {len(self.issues)} 个问题将被修复")
        print("请确认您已备份数据库！")
        
        # 这里可以添加实际的修复逻辑
        # 由于安全考虑，实际修复需要用户确认
        print("\n🔧 修复功能需要手动实现")
        print("请根据上述修复建议手动执行SQL语句")
        
    def save_report(self, filename="database_validation_report.txt"):
        """保存验证报告到文件"""
        import io
        
        output = io.StringIO()
        original_stdout = sys.stdout
        sys.stdout = output
        
        # 重新运行验证并捕获输出
        asyncio.run(self.verify_all())
        
        sys.stdout = original_stdout
        report_content = output.getvalue()
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(report_content)
        
        print(f"📄 验证报告已保存到: {filename}")
        return filename


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="数据库验证工具")
    parser.add_argument("--db", help="数据库文件路径", default=None)
    parser.add_argument("--fix", help="尝试自动修复", action="store_true")
    parser.add_argument("--report", help="保存报告到文件", default=None)
    
    args = parser.parse_args()
    
    verifier = DatabaseVerifier(args.db)
    
    if args.report:
        verifier.save_report(args.report)
    else:
        await verifier.verify_all()
        
        if args.fix:
            await verifier.apply_fixes()


if __name__ == "__main__":
    asyncio.run(main())
