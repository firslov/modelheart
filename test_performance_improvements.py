#!/usr/bin/env python3
"""
性能改进测试脚本
验证优化后的性能提升效果
"""

import time
import json
from app.services.api_service import ApiService
from app.services.llm_service import LLMService

def test_token_caching():
    """测试token计算缓存性能"""
    print("🔍 测试token计算缓存性能...")
    
    api_service = ApiService()
    
    # 创建测试API密钥
    test_key = api_service.generate_api_key()
    
    # 测试数据
    test_messages = [
        {"role": "user", "content": "这是一个测试消息，用于验证token计算性能。"},
        {"role": "assistant", "content": "好的，我明白了。这是一个回复消息。"},
        {"role": "user", "content": "请继续测试，看看缓存机制是否有效。"}
    ]
    
    # 第一次计算（无缓存）
    start_time = time.time()
    for i in range(100):
        request_data = {"messages": test_messages}
        api_service.update_usage(test_key, request_data)
    first_run_time = time.time() - start_time
    
    # 第二次计算（有缓存）
    start_time = time.time()
    for i in range(100):
        request_data = {"messages": test_messages}
        api_service.update_usage(test_key, request_data)
    second_run_time = time.time() - start_time
    
    print(f"📊 第一次运行（无缓存）: {first_run_time:.4f}秒")
    print(f"📊 第二次运行（有缓存）: {second_run_time:.4f}秒")
    
    if second_run_time < first_run_time:
        improvement = (first_run_time - second_run_time) / first_run_time * 100
        print(f"✅ 性能提升: {improvement:.1f}%")
    else:
        print("⚠️  缓存效果不明显，可能需要调整缓存策略")

def test_stats_caching():
    """测试统计信息缓存性能"""
    print("\n🔍 测试统计信息缓存性能...")
    
    api_service = ApiService()
    
    # 添加一些测试数据
    for i in range(10):
        api_service.api_usage[f"test_key_{i}"] = api_service.api_usage.get(f"test_key_{i}", 
            type('ApiKeyUsage', (), {
                'usage': i * 1000,
                'limit': 1000000,
                'reqs': i * 10,
                'phone': f"1380013800{i}",
                'created_at': '2024-01-01',
                'last_used': '2024-01-01'
            })()
        )
    
    # 第一次获取统计信息
    start_time = time.time()
    for i in range(50):
        stats = api_service.get_usage_stats()
    first_run_time = time.time() - start_time
    
    # 第二次获取统计信息（使用缓存）
    start_time = time.time()
    for i in range(50):
        stats = api_service.get_usage_stats()
    second_run_time = time.time() - start_time
    
    print(f"📊 第一次运行（无缓存）: {first_run_time:.4f}秒")
    print(f"📊 第二次运行（有缓存）: {second_run_time:.4f}秒")
    
    if second_run_time < first_run_time:
        improvement = (first_run_time - second_run_time) / first_run_time * 100
        print(f"✅ 性能提升: {improvement:.1f}%")
    else:
        print("⚠️  缓存效果不明显")

def test_llm_service_initialization():
    """测试LLM服务初始化性能"""
    print("\n🔍 测试LLM服务初始化性能...")
    
    llm_service = LLMService()
    
    # 先初始化服务
    import asyncio
    asyncio.run(llm_service.initialize())
    
    # 测试初始化
    start_time = time.time()
    for i in range(10):
        llm_service._connection_pool_stats["last_check"] = 0  # 重置检查时间
        # 模拟连接池监控调用
        asyncio.run(llm_service._monitor_connection_pool())
    init_time = time.time() - start_time
    
    print(f"📊 连接池监控平均时间: {init_time/10:.4f}秒")
    print("✅ LLM服务初始化正常")

def main():
    """主测试函数"""
    print("🚀 开始性能改进测试...")
    print("=" * 50)
    
    try:
        test_token_caching()
        test_stats_caching()
        test_llm_service_initialization()
        
        print("\n" + "=" * 50)
        print("🎉 所有测试完成！")
        print("📋 性能改进总结:")
        print("   • Token计算缓存机制")
        print("   • 统计信息缓存优化") 
        print("   • 连接池监控频率优化")
        print("   • 文件读取频率优化")
        print("   • 错误处理策略优化")
        
    except Exception as e:
        print(f"❌ 测试过程中出现错误: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
