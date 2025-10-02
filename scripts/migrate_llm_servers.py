#!/usr/bin/env python3
"""
LLM服务器数据迁移脚本
将JSON文件中的LLM服务器配置迁移到SQLite数据库
"""

import json
import asyncio
import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.database import get_db_session
from app.database.models import LLMServer, ServerModel


async def migrate_llm_servers():
    """迁移LLM服务器数据"""
    
    llm_servers_file = "llm_servers_list.json"
    
    if not os.path.exists(llm_servers_file):
        print(f"错误: LLM服务器文件 {llm_servers_file} 不存在")
        return
    
    print(f"开始迁移LLM服务器数据从 {llm_servers_file}...")
    
    try:
        # 读取JSON数据
        with open(llm_servers_file, 'r', encoding='utf-8') as f:
            llm_servers_data = json.load(f)
        
        print(f"找到 {len(llm_servers_data)} 个LLM服务器配置")
        
        # 使用数据库会话
        async for session in get_db_session():
            migrated_count = 0
            
            for server_url, server_config in llm_servers_data.items():
                print(f"迁移服务器: {server_url}")
                
                # 检查服务器是否已存在
                existing_server = await session.get(LLMServer, server_url)
                
                if existing_server:
                    print(f"  服务器 {server_url} 已存在，跳过")
                    continue
                
                # 创建新的服务器记录
                llm_server = LLMServer(
                    server_url=server_url,
                    device=server_config.get('device', ''),
                    apikey=server_config.get('apikey', '')
                )
                
                # 添加模型配置
                models_data = server_config.get('model', {})
                for actual_model_name, model_data in models_data.items():
                    server_model = ServerModel(
                        client_model_name=model_data.get('name', actual_model_name),  # 实际后端模型名称
                        actual_model_name=actual_model_name,  # 前端使用的模型名称
                        reqs=model_data.get('reqs', 0),
                        status=model_data.get('status', True)
                    )
                    llm_server.models.append(server_model)
                
                session.add(llm_server)
                migrated_count += 1
                print(f"  添加服务器: {server_url} (包含 {len(models_data)} 个模型)")
            
            await session.commit()
            print(f"成功迁移 {migrated_count} 个LLM服务器配置")
            
    except Exception as e:
        print(f"迁移过程中发生错误: {e}")
        import traceback
        traceback.print_exc()


async def check_existing_servers():
    """检查数据库中现有的LLM服务器"""
    
    print("检查数据库中现有的LLM服务器...")
    
    try:
        async for session in get_db_session():
            from sqlalchemy import select
            from sqlalchemy.orm import selectinload
            
            result = await session.execute(
                select(LLMServer).options(selectinload(LLMServer.models))
            )
            existing_servers = result.scalars().all()
            
            print(f"数据库中现有 {len(existing_servers)} 个LLM服务器:")
            for server in existing_servers:
                print(f"  - {server.server_url} (包含 {len(server.models)} 个模型)")
            
    except Exception as e:
        print(f"检查现有服务器时发生错误: {e}")


async def main():
    """主函数"""
    
    print("LLM服务器数据迁移工具")
    print("=" * 50)
    
    # 首先检查现有服务器
    await check_existing_servers()
    
    print("\n" + "=" * 50)
    
    # 执行迁移
    await migrate_llm_servers()
    
    print("\n" + "=" * 50)
    
    # 再次检查迁移后的服务器
    await check_existing_servers()
    
    print("\n迁移完成！")


if __name__ == "__main__":
    asyncio.run(main())
