#!/usr/bin/env python3
"""
API密钥数据迁移脚本
将JSON文件中的API密钥使用数据迁移到SQLite数据库
"""

import json
import asyncio
import sys
import os
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.database import get_db_session
from app.database.models import ApiKey, ModelUsage


async def migrate_api_keys():
    """迁移API密钥数据"""
    
    api_keys_file = "api_keys_usage.json"
    
    if not os.path.exists(api_keys_file):
        print(f"错误: API密钥文件 {api_keys_file} 不存在")
        return
    
    print(f"开始迁移API密钥数据从 {api_keys_file}...")
    
    try:
        # 读取JSON数据
        with open(api_keys_file, 'r', encoding='utf-8') as f:
            api_keys_data = json.load(f)
        
        print(f"找到 {len(api_keys_data)} 个API密钥配置")
        
        # 使用数据库会话
        async for session in get_db_session():
            migrated_count = 0
            
            for api_key_str, key_data in api_keys_data.items():
                print(f"迁移API密钥: {api_key_str}")
                
                # 检查API密钥是否已存在
                from sqlalchemy import select
                result = await session.execute(
                    select(ApiKey).where(ApiKey.api_key == api_key_str)
                )
                existing_key = result.scalar_one_or_none()
                
                if existing_key:
                    print(f"  API密钥 {api_key_str} 已存在，跳过")
                    continue
                
                # 解析日期时间
                created_at = None
                last_used = None
                
                try:
                    if key_data.get('created_at'):
                        created_at = datetime.strptime(key_data['created_at'], "%Y-%m-%d")
                except:
                    created_at = datetime.now()
                
                try:
                    if key_data.get('last_used'):
                        last_used = datetime.strptime(key_data['last_used'], "%Y-%m-%d %H:%M:%S")
                except:
                    last_used = datetime.now()
                
                # 创建新的API密钥记录
                api_key = ApiKey(
                    api_key=api_key_str,
                    usage=key_data.get('usage', 0),
                    limit_value=key_data.get('limit', 1000000),
                    reqs=key_data.get('reqs', 0),
                    created_at=created_at,
                    last_used=last_used,
                    phone=key_data.get('phone'),
                    created_at_str=key_data.get('created_at'),
                    last_used_str=key_data.get('last_used')
                )
                
                # 添加模型使用统计
                model_usage_data = key_data.get('model_usage', {})
                for model_name, model_data in model_usage_data.items():
                    model_usage = ModelUsage(
                        api_key_id=api_key.id,
                        model_name=model_name,
                        requests=model_data.get('requests', 0),
                        tokens=model_data.get('tokens', 0)
                    )
                    api_key.model_usages.append(model_usage)
                
                session.add(api_key)
                migrated_count += 1
                
                if migrated_count % 10 == 0:
                    print(f"  已迁移 {migrated_count} 个API密钥...")
            
            await session.commit()
            print(f"成功迁移 {migrated_count} 个API密钥配置")
            
    except Exception as e:
        print(f"迁移过程中发生错误: {e}")
        import traceback
        traceback.print_exc()


async def check_existing_keys():
    """检查数据库中现有的API密钥"""
    
    print("检查数据库中现有的API密钥...")
    
    try:
        async for session in get_db_session():
            from sqlalchemy import select
            
            result = await session.execute(select(ApiKey))
            existing_keys = result.scalars().all()
            
            print(f"数据库中现有 {len(existing_keys)} 个API密钥:")
            
            # 显示前10个密钥的摘要信息
            for i, key in enumerate(existing_keys[:10]):
                print(f"  - {key.api_key}: 使用量={key.usage}, 请求数={key.reqs}")
            
            if len(existing_keys) > 10:
                print(f"  ... 还有 {len(existing_keys) - 10} 个密钥")
            
    except Exception as e:
        print(f"检查现有密钥时发生错误: {e}")


async def main():
    """主函数"""
    
    print("API密钥数据迁移工具")
    print("=" * 50)
    
    # 首先检查现有密钥
    await check_existing_keys()
    
    print("\n" + "=" * 50)
    
    # 执行迁移
    await migrate_api_keys()
    
    print("\n" + "=" * 50)
    
    # 再次检查迁移后的密钥
    await check_existing_keys()
    
    print("\n迁移完成！")


if __name__ == "__main__":
    asyncio.run(main())
