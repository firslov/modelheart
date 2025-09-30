from typing import Dict, Optional, List
import json
import os
import time
from fastapi import HTTPException
from app.models.api_models import ApiKeyUsage, UsageStats
from app.utils.helpers import generate_token, get_current_time, log_api_usage
from app.config.settings import settings
import tiktoken


class ApiService:
    """API服务管理类"""

    def __init__(self):
        self.api_usage: Dict[str, ApiKeyUsage] = {}
        self.encoding = tiktoken.encoding_for_model(settings.TOKENIZER_MODEL)
        self.llm_servers_cache = {}
        self.last_modified = 0  # 记录配置文件最后修改时间
        self._token_cache = {}  # 添加token缓存
        self._stats_cache = None  # 统计缓存
        self._stats_last_updated = 0
        self.load_llm_servers()

    def validate_api_key(self, api_key: str) -> None:
        """验证API密钥

        Args:
            api_key: API密钥

        Raises:
            HTTPException: 无效的API密钥
        """
        if not api_key or api_key not in self.api_usage:
            raise HTTPException(401, "Invalid API Key")

    def check_usage_limit(self, api_key: str) -> None:
        """检查使用限额

        Args:
            api_key: API密钥

        Raises:
            HTTPException: 超出使用限额
        """
        usage = self.api_usage[api_key]
        if usage.usage >= usage.limit:
            raise HTTPException(402, "Usage limit exceeded")

    def generate_api_key(self) -> str:
        """生成新的API密钥

        Returns:
            str: 新生成的API密钥
        """
        new_key = generate_token()
        self.api_usage[new_key] = ApiKeyUsage(
            limit=settings.DEFAULT_LIMIT, created_at=get_current_time()
        )
        return new_key

    def update_usage(self, api_key: str, request_data: Dict, model: str = None) -> None:
        """更新API使用情况，优化token计算

        Args:
            api_key: API密钥
            request_data: 请求数据
            model: 模型名称
        """
        usage = self.api_usage[api_key]
        usage.last_used = get_current_time()
        usage.reqs += 1

        # 优化token计算：使用缓存
        total_tokens = 0
        for m in request_data.get("messages", []):
            content = m.get("content", "")
            if isinstance(content, str):
                # 使用缓存避免重复计算
                cache_key = hash(content)
                if cache_key in self._token_cache:
                    total_tokens += self._token_cache[cache_key]
                else:
                    token_count = len(self.encoding.encode(content))
                    self._token_cache[cache_key] = token_count
                    total_tokens += token_count

        usage.usage += total_tokens

        # 更新模型使用统计
        if model:
            if model not in usage.model_usage:
                from app.models.api_models import ModelUsage

                usage.model_usage[model] = ModelUsage()

            usage.model_usage[model].requests += 1
            usage.model_usage[model].tokens += total_tokens

        # 限制缓存大小
        if len(self._token_cache) > 1000:
            # 移除最旧的缓存项
            oldest_key = next(iter(self._token_cache))
            del self._token_cache[oldest_key]

        # log_api_usage(api_key, usage.dict())

    def get_usage_stats(self) -> UsageStats:
        """获取使用统计信息 - 添加缓存优化

        Returns:
            UsageStats: 使用统计信息
        """
        current_time = time.time()

        # 如果缓存有效且未过期（5秒内），直接返回缓存
        if self._stats_cache and current_time - self._stats_last_updated < 5:
            return self._stats_cache

        # 重新计算统计信息
        stats = UsageStats(
            current_time=get_current_time(),
            total_usage=sum(info.usage for info in self.api_usage.values()),
            total_entries=len(self.api_usage),
            total_reqs=sum(info.reqs for info in self.api_usage.values()),
        )

        # 统计不同使用量区间的数量
        for info in self.api_usage.values():
            if info.usage < 100:
                stats.less_than_100 += 1
            elif info.usage < 10000:
                stats.between_100_and_10000 += 1
            else:
                stats.more_than_10000 += 1

        # 生成API密钥使用详情
        stats.api_keys = [
            {
                "key": key[-6:],
                "phone": info.phone,
                "usage": info.usage,
                "limit": info.limit,
                "reqs": info.reqs,
                "created_at": info.created_at,
                "last_used": info.last_used,
            }
            for key, info in sorted(
                self.api_usage.items(), key=lambda x: x[1].usage, reverse=True
            )
            if info.usage > 0
        ]

        # 更新缓存
        self._stats_cache = stats
        self._stats_last_updated = current_time

        return stats

    async def reset_monthly_usage(self) -> None:
        """重置每月使用量"""
        for key in self.api_usage:
            self.api_usage[key].usage = 0
            self.api_usage[key].reqs = 0

    def load_llm_servers(self) -> None:
        """加载LLM服务器配置到缓存 - 优化文件检查频率"""
        try:
            if not os.path.exists(settings.LLM_SERVERS_FILE):
                self.llm_servers_cache = {}
                return

            # 减少文件系统调用频率
            current_time = time.time()
            if current_time - self.last_modified < 1:  # 1秒内不重复检查
                return

            current_mtime = os.path.getmtime(settings.LLM_SERVERS_FILE)
            if current_mtime > self.last_modified:
                with open(settings.LLM_SERVERS_FILE, "r", encoding="utf-8") as f:
                    self.llm_servers_cache = json.load(f)
                self.last_modified = current_mtime
        except Exception as e:
            self.llm_servers_cache = {}
            raise RuntimeError(f"Failed to load LLM servers: {str(e)}")

    def save_llm_servers(self) -> None:
        """将缓存中的LLM服务器配置保存到文件"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(settings.LLM_SERVERS_FILE), exist_ok=True)
            with open(settings.LLM_SERVERS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.llm_servers_cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            raise RuntimeError(f"Failed to save LLM servers: {str(e)}")

    def increment_model_reqs(self, server_url: str, model_name: str) -> None:
        """增加模型请求计数

        Args:
            server_url: 服务器URL
            model_name: 模型名称
        """
        if server_url in self.llm_servers_cache:
            models = self.llm_servers_cache[server_url].get("model", {})
            if model_name in models:
                models[model_name]["reqs"] = models[model_name].get("reqs", 0) + 1
                # 异步保存到文件
                self.save_llm_servers()
