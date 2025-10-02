#!/usr/bin/env python3
"""
数据库初始化脚本
创建所有必要的数据库表结构
"""

import asyncio
import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.database import init_db


async def main():
    """主函数"""
    print("初始化数据库表结构...")
    
    try:
        await init_db()
        print("数据库表结构创建成功！")
    except Exception as e:
        print(f"初始化数据库时发生错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
