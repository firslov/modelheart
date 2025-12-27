from typing import Dict, Optional, List
import json
import os
import time
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_
from fastapi import HTTPException
from app.models.api_models import ApiKeyUsage, UsageStats
from app.utils.helpers import generate_token, get_current_time, log_api_usage
from app.config.settings import settings
from app.database.database import get_db_session
from app.database.models import ApiKey, ModelUsage, LLMServer, ServerModel
import tiktoken


class ApiService:
    """API服务管理类"""

    def __init__(self):
        # 尝试初始化tiktoken编码，如果失败则使用简单的字符计数作为回退
        try:
            self.encoding = tiktoken.encoding_for_model(settings.TOKENIZER_MODEL)
            self._use_tiktoken = True
        except Exception as e:
            # 如果tiktoken初始化失败（例如网络问题），使用简单的字符计数
            print(f"Warning: tiktoken initialization failed: {e}. Using fallback token counting.")
            self.encoding = None
            self._use_tiktoken = False
        
        # 改进的token缓存：使用LRU缓存策略
        self._token_cache = {}  # token缓存
        self._token_cache_keys = []  # 用于LRU管理的key列表
        self._max_token_cache_size = 1000  # 最大缓存大小
        
        # 模型权重缓存
        self._model_weights_cache = {}  # 模型权重缓存
        self._model_weights_last_updated = 0  # 最后更新时间
        self._model_weights_cache_ttl = 60  # 缓存TTL（秒）
        
        self._stats_cache = None  # 统计缓存
        self._stats_last_updated = 0

    async def validate_api_key(self, api_key: str, session: AsyncSession) -> None:
        """验证API密钥

        Args:
            api_key: API密钥
            session: 数据库会话

        Raises:
            HTTPException: 无效的API密钥
        """
        try:
            if not api_key:
                raise HTTPException(401, "Invalid API Key")
            
            result = await session.execute(
                select(ApiKey).where(ApiKey.api_key == api_key)
            )
            api_key_record = result.scalar_one_or_none()
            
            if not api_key_record:
                raise HTTPException(401, "Invalid API Key")
        except HTTPException:
            raise
        except Exception as e:
            # 记录数据库查询错误
            import logging
            logging.error(f"Database error in validate_api_key: {e}")
            raise HTTPException(500, "Internal server error during API key validation")

    async def check_usage_limit(self, api_key: str, session: AsyncSession) -> None:
        """检查使用限额

        Args:
            api_key: API密钥
            session: 数据库会话

        Raises:
            HTTPException: 超出使用限额
        """
        try:
            result = await session.execute(
                select(ApiKey).where(ApiKey.api_key == api_key)
            )
            api_key_record = result.scalar_one_or_none()
            
            if api_key_record and api_key_record.usage >= api_key_record.limit_value:
                raise HTTPException(402, "Usage limit exceeded")
        except HTTPException:
            raise
        except Exception as e:
            # 记录数据库查询错误
            import logging
            logging.error(f"Database error in check_usage_limit: {e}")
            raise HTTPException(500, "Internal server error during usage limit check")

    async def generate_api_key(self, session: AsyncSession) -> str:
        """生成新的API密钥

        Args:
            session: 数据库会话

        Returns:
            str: 新生成的API密钥
        """
        try:
            new_key = generate_token()
            
            # 检查是否已存在
            result = await session.execute(
                select(ApiKey).where(ApiKey.api_key == new_key)
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                # 如果已存在，重新生成
                return await self.generate_api_key(session)
            
            # 创建新的API密钥记录
            api_key = ApiKey(
                api_key=new_key,
                limit_value=settings.DEFAULT_LIMIT,
                created_at_str=get_current_time()
            )
            session.add(api_key)
            await session.commit()
            
            return new_key
        except Exception as e:
            # 回滚事务并记录错误
            await session.rollback()
            import logging
            logging.error(f"Error generating API key: {e}")
            raise HTTPException(500, "Failed to generate API key")

    async def update_usage(self, api_key: str, request_data: Dict, model: str = None, session: AsyncSession = None) -> None:
        """更新API使用情况，根据模型权重计算token

        Args:
            api_key: API密钥
            request_data: 请求数据
            model: 模型名称
            session: 数据库会话
        """
        if session is None:
            async for db_session in get_db_session():
                await self._update_usage_internal(api_key, request_data, model, db_session)
                return
        else:
            await self._update_usage_internal(api_key, request_data, model, session)

    async def _get_model_weights(self, model: str, session: AsyncSession) -> tuple[float, float]:
        """获取模型权重，使用缓存优化
        
        Args:
            model: 模型名称
            session: 数据库会话
            
        Returns:
            tuple: (input_weight, output_weight)
        """
        current_time = time.time()
        
        # 检查缓存是否有效
        cache_key = model
        if (cache_key in self._model_weights_cache and 
            current_time - self._model_weights_last_updated < self._model_weights_cache_ttl):
            return self._model_weights_cache[cache_key]
        
        # 从数据库获取模型权重配置，支持新旧字段
        from sqlalchemy.orm import selectinload
        from sqlalchemy import or_
        
        # 同时查询新旧字段：前端模型名称可能是actual_model_name或frontend_model_name
        result = await session.execute(
            select(ServerModel)
            .where(
                or_(
                    ServerModel.actual_model_name == model,  # 旧字段
                    ServerModel.frontend_model_name == model  # 新字段
                )
            )
            .options(selectinload(ServerModel.server))
        )
        server_models = result.scalars().all()
        
        # 默认权重
        input_weight = 1.0
        output_weight = 1.0
        
        if server_models:
            # 优先选择启用的模型
            enabled_models = [m for m in server_models if m.status]
            if enabled_models:
                server_model = enabled_models[0]
            else:
                server_model = server_models[0]  # 如果没有启用的，使用第一个
            
            input_weight = server_model.input_token_weight
            output_weight = server_model.output_token_weight
        
        # 更新缓存
        self._model_weights_cache[cache_key] = (input_weight, output_weight)
        self._model_weights_last_updated = current_time
        
        return input_weight, output_weight

    async def _update_usage_internal(self, api_key: str, request_data: Dict, model: str, session: AsyncSession) -> None:
        """内部更新使用情况方法 - 使用SELECT FOR UPDATE防止并发竞争条件"""
        try:
            # 使用SELECT FOR UPDATE锁定API密钥记录，防止并发更新
            from sqlalchemy import select, update, and_
            
            result = await session.execute(
                select(ApiKey)
                .where(ApiKey.api_key == api_key)
                .with_for_update()  # 锁定记录，防止并发更新
            )
            api_key_record = result.scalar_one_or_none()
            
            if not api_key_record:
                return

            # 更新最后使用时间
            api_key_record.last_used = datetime.now()
            api_key_record.last_used_str = get_current_time()
            api_key_record.reqs += 1

            # 获取模型权重（使用缓存优化）
            input_weight = 1.0
            output_weight = 1.0
            
            if model:
                input_weight, output_weight = await self._get_model_weights(model, session)

            # 计算加权token数量
            weighted_tokens = 0
            
            # 从响应中获取实际的input和output token数量
            if "usage" in request_data:
                # 如果请求数据中已经包含usage信息（来自上游响应）
                usage_data = request_data["usage"]
                prompt_tokens = usage_data.get("prompt_tokens", 0)
                
                # 处理embeddings接口的特殊情况（只有prompt_tokens和total_tokens）
                if "completion_tokens" in usage_data:
                    completion_tokens = usage_data.get("completion_tokens", 0)
                elif "total_tokens" in usage_data:
                    # embeddings接口：total_tokens = prompt_tokens
                    completion_tokens = 0
                else:
                    completion_tokens = 0
                
                # 应用权重计算
                weighted_tokens = (prompt_tokens * input_weight) + (completion_tokens * output_weight)
            else:
                # 回退到基于消息内容的估算
                prompt_tokens = 0
                for m in request_data.get("messages", []):
                    content = m.get("content", "")
                    if isinstance(content, str):
                        # 使用改进的缓存机制
                        cache_key = hash(content)
                        if cache_key in self._token_cache:
                            prompt_tokens += self._token_cache[cache_key]
                            # 更新LRU：将最近使用的key移到列表末尾
                            if cache_key in self._token_cache_keys:
                                self._token_cache_keys.remove(cache_key)
                            self._token_cache_keys.append(cache_key)
                        else:
                            if self._use_tiktoken and self.encoding:
                                # 使用tiktoken计算token数量
                                token_count = len(self.encoding.encode(content))
                            else:
                                # 改进的回退方案：使用更准确的字符计数算法
                                # 中文大约1.5个字符=1个token，英文大约4个字符=1个token
                                chinese_chars = sum(1 for c in content if '\u4e00' <= c <= '\u9fff')
                                english_chars = len(content) - chinese_chars
                                token_count = max(1, int(chinese_chars / 1.5 + english_chars / 4))
                            
                            # 添加到缓存
                            self._token_cache[cache_key] = token_count
                            self._token_cache_keys.append(cache_key)
                            prompt_tokens += token_count
                            
                            # 检查缓存大小，使用LRU策略清理
                            if len(self._token_cache) > self._max_token_cache_size:
                                # 移除最久未使用的缓存项
                                oldest_key = self._token_cache_keys.pop(0)
                                del self._token_cache[oldest_key]
                
                # 估算output tokens（假设为input tokens的1/3）
                completion_tokens = max(1, int(prompt_tokens * 0.33))
                
                # 应用权重计算
                weighted_tokens = (prompt_tokens * input_weight) + (completion_tokens * output_weight)

            api_key_record.usage += weighted_tokens

            # 更新模型使用统计 - 同样需要锁定
            if model:
                # 使用SELECT FOR UPDATE锁定模型使用记录，使用first()而不是scalar_one_or_none()
                result = await session.execute(
                    select(ModelUsage)
                    .where(
                        and_(
                            ModelUsage.api_key_id == api_key_record.id,
                            ModelUsage.model_name == model
                        )
                    )
                    .with_for_update()  # 锁定记录，防止并发更新
                )
                model_usage_result = result.first()
                
                if not model_usage_result:
                    model_usage = ModelUsage(
                        api_key_id=api_key_record.id,
                        model_name=model,
                        requests=0,
                        tokens=0
                    )
                    session.add(model_usage)
                else:
                    model_usage = model_usage_result[0]
                
                model_usage.requests += 1
                model_usage.tokens += weighted_tokens

            await session.commit()
            # log_api_usage(api_key, api_key_record.to_dict())
            
        except Exception as e:
            # 回滚事务并记录错误
            await session.rollback()
            import logging
            logging.error(f"Error updating usage for API key {api_key}: {e}")
            # 不重新抛出异常，避免影响正常请求处理

    async def get_usage_stats(self, session: AsyncSession) -> UsageStats:
        """获取使用统计信息 - 添加缓存优化

        Args:
            session: 数据库会话

        Returns:
            UsageStats: 使用统计信息
        """
        current_time = time.time()

        # 如果缓存有效且未过期（5秒内），直接返回缓存
        if self._stats_cache and current_time - self._stats_last_updated < 5:
            return self._stats_cache

        # 从数据库获取统计信息
        result = await session.execute(
            select(ApiKey)
        )
        all_api_keys = result.scalars().all()

        # 计算统计信息
        total_usage = sum(key.usage for key in all_api_keys)
        total_entries = len(all_api_keys)
        total_reqs = sum(key.reqs for key in all_api_keys)

        stats = UsageStats(
            current_time=get_current_time(),
            total_usage=total_usage,
            total_entries=total_entries,
            total_reqs=total_reqs,
        )

        # 统计不同使用量区间的数量
        for key in all_api_keys:
            if key.usage < 100:
                stats.less_than_100 += 1
            elif key.usage < 10000:
                stats.between_100_and_10000 += 1
            else:
                stats.more_than_10000 += 1

        # 生成API密钥使用详情
        stats.api_keys = [
            {
                "key": key.api_key[-6:],
                "phone": key.phone,
                "usage": key.usage,
                "limit": key.limit_value,
                "reqs": key.reqs,
                "created_at": key.created_at_str or (key.created_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(key.created_at, 'strftime') else str(key.created_at)),
                "last_used": key.last_used_str or (key.last_used.strftime("%Y-%m-%d %H:%M:%S") if key.last_used and hasattr(key.last_used, 'strftime') else str(key.last_used) if key.last_used else None),
            }
            for key in sorted(all_api_keys, key=lambda x: x.usage, reverse=True)
            if key.usage > 0
        ]

        # 更新缓存
        self._stats_cache = stats
        self._stats_last_updated = current_time

        return stats

    async def reset_monthly_usage(self, session: AsyncSession) -> None:
        """重置每月使用量

        Args:
            session: 数据库会话
        """
        # 重置所有API密钥的使用量
        await session.execute(
            update(ApiKey).values(usage=0, reqs=0)
        )
        
        # 重置所有模型使用统计
        await session.execute(
            update(ModelUsage).values(requests=0, tokens=0)
        )
        
        await session.commit()

    async def load_llm_servers(self, session: AsyncSession) -> Dict:
        """加载LLM服务器配置

        Args:
            session: 数据库会话

            Returns:
                Dict: LLM服务器配置
        """
        from sqlalchemy.orm import selectinload
        
        result = await session.execute(
            select(LLMServer).options(selectinload(LLMServer.models))
        )
        servers = result.scalars().all()
        
        servers_dict = {}
        for server in servers:
            # 手动构建服务器配置，避免异步延迟加载问题
            server_config = {
                "server_url": server.server_url,
                "model": {},
                "apikey": server.apikey,
                "device": server.device,
                "enabled": True
            }
            
            # 手动构建模型映射 - 支持新旧字段
            for model in server.models:
                # 获取前端模型名称（优先使用新字段）
                frontend_name = model.frontend_model_name or model.actual_model_name
                # 获取后端模型名称（优先使用新字段）
                backend_name = model.backend_model_name or model.client_model_name
                
                server_config["model"][frontend_name] = {
                    "name": backend_name,  # 实际后端模型名称
                    "reqs": model.reqs,
                    "status": model.status,
                    "input_token_weight": model.input_token_weight,
                    "output_token_weight": model.output_token_weight
                }
            
            servers_dict[server.server_url] = server_config
        
        return servers_dict

    async def save_llm_servers(self, servers_data: Dict, session: AsyncSession) -> None:
        """保存LLM服务器配置 - 替换整个服务器列表

        Args:
            servers_data: 服务器配置数据
            session: 数据库会话
        """
        from sqlalchemy import delete
        from sqlalchemy.exc import IntegrityError
        
        try:
            # 先删除所有现有服务器配置
            # 使用delete语句而不是session.delete()，确保级联删除正常工作
            await session.execute(delete(ServerModel))
            await session.execute(delete(LLMServer))
            
            # 添加新的服务器配置
            for server_url, server_data in servers_data.items():
                llm_server = LLMServer(
                    server_url=server_url,
                    device=server_data.get('device'),
                    apikey=server_data.get('apikey')
                )
                
                # 添加模型配置 - 同时设置新旧字段以确保兼容性
                models_data = server_data.get('model', {})
                for frontend_model_name, model_data in models_data.items():
                    backend_model_name = model_data.get('name', frontend_model_name)
                    
                    server_model = ServerModel(
                        # 旧字段（保持兼容）
                        client_model_name=backend_model_name,  # 实际后端模型名称
                        actual_model_name=frontend_model_name,  # 前端使用的模型名称
                        # 新字段（更清晰的命名）
                        backend_model_name=backend_model_name,  # 实际后端模型名称
                        frontend_model_name=frontend_model_name,  # 前端使用的模型名称
                        reqs=model_data.get('reqs', 0),
                        status=model_data.get('status', True),
                        input_token_weight=model_data.get('input_token_weight', 1.0),
                        output_token_weight=model_data.get('output_token_weight', 1.0)
                    )
                    llm_server.models.append(server_model)
                
                session.add(llm_server)
            
            await session.commit()
            
        except IntegrityError as e:
            # 回滚事务
            await session.rollback()
            # 记录错误并重新抛出
            import logging
            logging.error(f"数据库完整性错误: {e}")
            raise HTTPException(400, f"数据库完整性错误: 可能存在重复的模型配置")
        except Exception as e:
            # 回滚事务
            await session.rollback()
            import logging
            logging.error(f"保存LLM服务器时出错: {e}")
            raise

    async def update_llm_server(self, server_url: str, server_data: Dict, session: AsyncSession) -> None:
        """更新单个LLM服务器配置

        Args:
            server_url: 服务器URL
            server_data: 服务器配置数据
            session: 数据库会话
        """
        from sqlalchemy.orm import selectinload
        from sqlalchemy import delete
        from sqlalchemy.exc import IntegrityError
        
        try:
            # 查找现有服务器
            result = await session.execute(
                select(LLMServer)
                .where(LLMServer.server_url == server_url)
                .options(selectinload(LLMServer.models))
            )
            existing_server = result.scalar_one_or_none()
            
            if existing_server:
                # 更新服务器信息
                existing_server.device = server_data.get('device', existing_server.device)
                existing_server.apikey = server_data.get('apikey', existing_server.apikey)
                
                # 获取新的模型配置
                models_data = server_data.get('model', {})
                
                # 创建现有模型的映射，用于保留请求计数（支持新旧字段）
                existing_models_map = {}
                for model in existing_server.models:
                    # 使用前端模型名称作为key，支持新旧字段
                    frontend_name = model.frontend_model_name or model.actual_model_name
                    existing_models_map[frontend_name] = model
                
                # 删除不存在的模型，更新或添加新的模型
                models_to_delete = []
                for existing_model in existing_server.models:
                    frontend_name = existing_model.frontend_model_name or existing_model.actual_model_name
                    if frontend_name not in models_data:
                        models_to_delete.append(existing_model)
                
                # 删除不存在的模型
                for model_to_delete in models_to_delete:
                    existing_server.models.remove(model_to_delete)
                    # 确保从数据库中删除
                    await session.delete(model_to_delete)
                
                # 更新或添加模型
                for frontend_model_name, model_data in models_data.items():
                    backend_model_name = model_data.get('name', frontend_model_name)
                    
                    if frontend_model_name in existing_models_map:
                        # 更新现有模型
                        existing_model = existing_models_map[frontend_model_name]
                        # 更新旧字段
                        existing_model.client_model_name = backend_model_name  # 实际后端模型名称
                        existing_model.actual_model_name = frontend_model_name  # 前端使用的模型名称
                        # 更新新字段
                        existing_model.backend_model_name = backend_model_name  # 实际后端模型名称
                        existing_model.frontend_model_name = frontend_model_name  # 前端使用的模型名称
                        
                        existing_model.status = model_data.get('status', True)
                        existing_model.input_token_weight = model_data.get('input_token_weight', 1.0)
                        existing_model.output_token_weight = model_data.get('output_token_weight', 1.0)
                        # 保留原有的请求计数，除非明确指定新的值
                        if 'reqs' in model_data:
                            existing_model.reqs = model_data.get('reqs', 0)
                        # 确保模型被标记为已修改
                        session.add(existing_model)
                    else:
                        # 添加新模型
                        server_model = ServerModel(
                            # 旧字段（保持兼容）
                            client_model_name=backend_model_name,  # 实际后端模型名称
                            actual_model_name=frontend_model_name,  # 前端使用的模型名称
                            # 新字段（更清晰的命名）
                            backend_model_name=backend_model_name,  # 实际后端模型名称
                            frontend_model_name=frontend_model_name,  # 前端使用的模型名称
                            reqs=model_data.get('reqs', 0),
                            status=model_data.get('status', True),
                            input_token_weight=model_data.get('input_token_weight', 1.0),
                            output_token_weight=model_data.get('output_token_weight', 1.0)
                        )
                        existing_server.models.append(server_model)
            else:
                # 如果服务器不存在，创建新的
                llm_server = LLMServer(
                    server_url=server_url,
                    device=server_data.get('device'),
                    apikey=server_data.get('apikey')
                )
                
                # 添加模型配置 - 同时设置新旧字段
                models_data = server_data.get('model', {})
                for frontend_model_name, model_data in models_data.items():
                    backend_model_name = model_data.get('name', frontend_model_name)
                    
                    server_model = ServerModel(
                        # 旧字段（保持兼容）
                        client_model_name=backend_model_name,  # 实际后端模型名称
                        actual_model_name=frontend_model_name,  # 前端使用的模型名称
                        # 新字段（更清晰的命名）
                        backend_model_name=backend_model_name,  # 实际后端模型名称
                        frontend_model_name=frontend_model_name,  # 前端使用的模型名称
                        reqs=model_data.get('reqs', 0),
                        status=model_data.get('status', True),
                        input_token_weight=model_data.get('input_token_weight', 1.0),
                        output_token_weight=model_data.get('output_token_weight', 1.0)
                    )
                    llm_server.models.append(server_model)
                
                session.add(llm_server)
            
            await session.commit()
            
        except IntegrityError as e:
            # 回滚事务
            await session.rollback()
            # 记录错误并重新抛出
            print(f"数据库完整性错误: {e}")
            raise HTTPException(400, f"数据库完整性错误: 可能存在重复的模型配置")
        except Exception as e:
            # 回滚事务
            await session.rollback()
            print(f"更新LLM服务器时出错: {e}")
            raise

    async def update_anthropic_usage(self, api_key: str, model: str, session: AsyncSession) -> None:
        """更新Anthropic API使用情况 - 只增加请求计数，不计算token用量，防止并发竞争条件

        Args:
            api_key: API密钥
            model: 模型名称
            session: 数据库会话
        """
        try:
            # 使用SELECT FOR UPDATE锁定API密钥记录，防止并发更新
            from sqlalchemy import select, and_
            
            result = await session.execute(
                select(ApiKey)
                .where(ApiKey.api_key == api_key)
                .with_for_update()  # 锁定记录，防止并发更新
            )
            api_key_record = result.scalar_one_or_none()
            
            if not api_key_record:
                return

            # 更新最后使用时间
            api_key_record.last_used = datetime.now()
            api_key_record.last_used_str = get_current_time()
            
            # 只增加请求计数，不增加token用量
            api_key_record.reqs += 1

            # 更新模型使用统计 - 只增加请求计数，不增加token用量
            if model:
                # 使用SELECT FOR UPDATE锁定模型使用记录，使用first()而不是scalar_one_or_none()
                result = await session.execute(
                    select(ModelUsage)
                    .where(
                        and_(
                            ModelUsage.api_key_id == api_key_record.id,
                            ModelUsage.model_name == model
                        )
                    )
                    .with_for_update()  # 锁定记录，防止并发更新
                )
                model_usage_result = result.first()
                
                if not model_usage_result:
                    model_usage = ModelUsage(
                        api_key_id=api_key_record.id,
                        model_name=model,
                        requests=0,
                        tokens=0
                    )
                    session.add(model_usage)
                else:
                    model_usage = model_usage_result[0]
                
                model_usage.requests += 1
                # tokens保持为0，因为Anthropic路由不计算token用量

            await session.commit()
            
        except Exception as e:
            # 回滚事务并记录错误
            await session.rollback()
            import logging
            logging.error(f"Error updating Anthropic usage for API key {api_key}: {e}")
            # 不重新抛出异常，避免影响正常请求处理

    async def increment_model_reqs(self, server_url: str, model_name: str, session: AsyncSession) -> None:
        """增加模型请求计数

        Args:
            server_url: 服务器URL
            model_name: 模型名称（前端使用的模型名称）
            session: 数据库会话
        """
        from sqlalchemy.orm import selectinload
        
        # 查找服务器，使用预加载避免延迟加载问题
        result = await session.execute(
            select(LLMServer)
            .where(LLMServer.server_url == server_url)
            .options(selectinload(LLMServer.models))
        )
        server = result.scalar_one_or_none()
        
        if server:
            # 查找模型 - 支持新旧字段
            for server_model in server.models:
                # 检查是否匹配前端模型名称（支持新旧字段）
                frontend_name = server_model.frontend_model_name or server_model.actual_model_name
                if frontend_name == model_name:
                    server_model.reqs += 1
                    await session.commit()
                    break
