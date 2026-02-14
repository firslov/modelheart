import json
from typing import Dict, Optional, Union, List
from collections import defaultdict
from urllib.parse import urlparse
import time
import socket
import asyncio

import httpx
from fastapi import HTTPException

from app.config.settings import settings
from app.models.api_models import AppState
from app.utils.logging_config import get_logger, log_forward, log_stream_complete, log_error
from app.utils.circuit_breaker import CircuitBreaker, CircuitState
from app.database.database import get_db_session
from app.database.models import LLMServer, ServerModel
from app.database.repositories import LLMServerRepository
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = get_logger(__name__)


class LLMService:
    """LLM服务管理类

    集成了熔断器模式，防止上游服务故障导致级联失败。
    """

    def __init__(self):
        self.http_client: Optional[httpx.AsyncClient] = None
        self.app_state = AppState()
        self._server_health = defaultdict(lambda: {"healthy": True, "last_check": 0})
        self._server_counters = defaultdict(int)

        # 初始化熔断器
        # 配置说明：
        # - failure_threshold: 连续失败 5 次后触发熔断
        # - recovery_timeout: 熔断后 30 秒尝试恢复
        # - half_open_max_calls: 半开状态最多 3 个试探请求
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=30.0,
            half_open_max_calls=3,
        )

        # 连接池调整锁，防止并发调整
        self._pool_adjustment_lock = asyncio.Lock()

    async def initialize(self) -> None:
        """初始化HTTP客户端 - 针对云服务器环境优化"""
        self.http_client = httpx.AsyncClient(
            limits=httpx.Limits(
                max_connections=500,  # 减少最大连接数，避免云服务器资源限制
                max_keepalive_connections=50,  # 减少保持连接数
                keepalive_expiry=180,  # 缩短保持连接时间
            ),
            timeout=httpx.Timeout(
                connect=10.0,  # 连接超时10秒
                read=None,  # 读取超时无限制（支持长对话）
                write=10.0,  # 写入超时10秒
                pool=10.0,  # 连接池超时10秒
            ),
            transport=httpx.AsyncHTTPTransport(
                retries=2,  # 减少重试次数，避免延迟累积
                http2=True,  # 启用HTTP/2
                socket_options=[
                    (socket.IPPROTO_TCP, socket.TCP_NODELAY, 1),  # 禁用Nagle算法
                    (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),  # 启用TCP保活
                ],
            ),
        )
        self._connection_pool_stats = {
            "last_check": time.time(),
            "active_connections": 0,
            "max_connections": 500,
            "adjustment_interval": 30,  # 每30秒检查一次，更频繁调整
        }
        logger.info("HTTP client initialized | connections=500 | http2=enabled")

    async def _monitor_connection_pool(self) -> None:
        """监控并动态调整连接池

        使用非阻塞锁检查，避免在高并发下产生锁竞争。
        """
        current_time = time.time()

        # 快速检查：如果未到检查时间，直接返回
        if (
            current_time - self._connection_pool_stats["last_check"]
            <= self._connection_pool_stats["adjustment_interval"]
        ):
            return

        # 尝试获取锁，如果锁被占用则跳过本次调整
        if self._pool_adjustment_lock.locked():
            return

        async with self._pool_adjustment_lock:
            # 双重检查：获取锁后再次确认是否需要调整
            if (
                current_time - self._connection_pool_stats["last_check"]
                <= self._connection_pool_stats["adjustment_interval"]
            ):
                return

            try:
                # 获取当前连接池状态
                pool = self.http_client._transport._pool
                active_connections = len(pool.connections)
                self._connection_pool_stats["active_connections"] = active_connections

                # 动态调整连接池大小
                usage_ratio = (
                    active_connections / self._connection_pool_stats["max_connections"]
                )

                if usage_ratio > 0.8:  # 使用率超过80%
                    new_max = min(
                        int(self._connection_pool_stats["max_connections"] * 1.2),
                        2000,  # 最大不超过2000
                    )
                    self.http_client._limits = httpx.Limits(
                        max_connections=new_max,
                        max_keepalive_connections=min(200, int(new_max * 0.1)),
                        keepalive_expiry=300,
                    )
                    self._connection_pool_stats["max_connections"] = new_max
                    logger.debug(f"pool expanded | connections={new_max} | usage={usage_ratio:.0%}")
                elif usage_ratio < 0.3:  # 使用率低于30%
                    new_max = max(
                        int(self._connection_pool_stats["max_connections"] * 0.8),
                        500,  # 最小不少于500
                    )
                    self.http_client._limits = httpx.Limits(
                        max_connections=new_max,
                        max_keepalive_connections=min(200, int(new_max * 0.1)),
                        keepalive_expiry=300,
                    )
                    self._connection_pool_stats["max_connections"] = new_max
                    logger.debug(f"pool reduced | connections={new_max} | usage={usage_ratio:.0%}")

                self._connection_pool_stats["last_check"] = current_time

            except Exception as e:
                logger.warning(f"pool monitor error | error={e}")

    async def cleanup(self) -> None:
        """清理资源"""
        if self.http_client:
            await self.http_client.aclose()

    async def init_llm_resources_from_db(self, session: AsyncSession) -> None:
        """从数据库初始化LLM资源

        Args:
            session: 数据库会话
        """
        # 使用Repository从数据库加载服务器配置
        llm_server_repo = LLMServerRepository(session, LLMServer)
        servers = await llm_server_repo.get_all_with_models()

        servers_data = {}
        for server in servers:
            # 手动构建服务器配置，避免异步延迟加载问题
            server_config = {
                "server_url": server.server_url,
                "model": {},
                "apikey": server.apikey,
                "enabled": True,  # 默认启用
            }

            # 手动构建模型映射 - 现在key是前端使用的模型名称，value是包含后端模型名称和token权重的对象
            for model in server.models:
                server_config["model"][model.actual_model_name] = {
                    "name": model.client_model_name,
                    "input_token_weight": model.input_token_weight or 1.0,
                    "output_token_weight": model.output_token_weight or 1.0,
                }

            servers_data[server.server_url] = server_config

        self.init_llm_resources(servers_data)

    def init_llm_resources(self, servers_data: Dict) -> None:
        """初始化LLM资源

        Args:
            servers_data: 服务器配置数据，model字段为key-value形式，key为客户使用的模型名，value为实际转发的模型名
        """
        self.app_state.llm_servers = servers_data
        self.app_state.cloud_models.clear()
        self.app_state.model_mapping.clear()
        self.app_state.model_name_mapping = {}  # 存储模型名称映射关系

        for server, config in servers_data.items():
            if isinstance(config["model"], dict):
                for client_model, target_model in config["model"].items():
                    self.app_state.model_mapping[client_model].append(server)
                    self.app_state.model_name_mapping[client_model] = target_model
                    if "apikey" in config:
                        self.app_state.cloud_models[client_model] = config["apikey"]
            else:
                # 兼容旧格式
                models = (
                    [config["model"]]
                    if isinstance(config["model"], str)
                    else config["model"]
                )
                for model in models:
                    self.app_state.model_mapping[model].append(server)
                    if "apikey" in config:
                        self.app_state.cloud_models[model] = config["apikey"]

    def _update_server_health(self, server: str, is_healthy: bool) -> None:
        """更新服务器健康状态"""
        self._server_health[server].update(
            {"healthy": is_healthy, "last_check": time.time()}
        )

    def _get_healthy_servers(self, servers: List[str]) -> List[str]:
        """获取健康的服务器列表，使用动态健康检查间隔"""
        current_time = time.time()
        healthy_servers = []

        for server in servers:
            health_info = self._server_health[server]

            # 动态计算健康检查间隔
            base_interval = 30  # 基础间隔30秒
            max_interval = 300  # 最大间隔5分钟
            error_count = health_info.get("error_count", 0)
            health_check_interval = min(base_interval * (2**error_count), max_interval)

            # 如果超过检查间隔，重置状态
            if (current_time - health_info["last_check"]) > health_check_interval:
                health_info["healthy"] = True
                health_info["error_count"] = max(0, error_count - 1)  # 逐步恢复

            # 如果服务器健康，加入列表
            if health_info["healthy"]:
                healthy_servers.append(server)

        # 如果没有健康服务器，返回所有服务器（降级模式）
        return healthy_servers or servers

    def _update_server_health(self, server: str, is_healthy: bool) -> None:
        """更新服务器健康状态，增加错误计数和响应时间记录"""
        health_info = self._server_health[server]
        health_info["healthy"] = is_healthy
        health_info["last_check"] = time.time()

        if not is_healthy:
            health_info["error_count"] = health_info.get("error_count", 0) + 1
        else:
            health_info["error_count"] = max(0, health_info.get("error_count", 0) - 1)

    def get_target_server(self, model: str) -> str:
        """获取目标服务器，使用加权轮询负载均衡

        结合熔断器状态，排除被熔断的服务器。

        Args:
            model: 模型名称

        Returns:
            str: 目标服务器URL

        Raises:
            HTTPException: 不支持的模型
        """
        servers = self.app_state.model_mapping.get(model, [])
        if not servers:
            raise HTTPException(400, f"Unsupported model: {model}")

        # 使用熔断器感知的健康检查
        healthy_servers = self._get_healthy_servers_with_circuit_breaker(servers)

        # 计算服务器权重
        weights = []
        for server in healthy_servers:
            health_info = self._server_health[server]

            # 基础权重
            weight = 100

            # 根据错误率调整权重
            error_count = health_info.get("error_count", 0)
            weight -= min(error_count * 10, 50)  # 每个错误减少10权重，最多减50

            # 根据响应时间调整权重（如果有记录）
            if "avg_response_time" in health_info:
                response_time = health_info["avg_response_time"]
                if response_time > 1000:  # 超过1秒
                    weight -= min(
                        (response_time - 1000) // 100, 30
                    )  # 每100ms减1，最多减30

            weights.append(max(weight, 10))  # 确保最小权重为10

        # 根据权重选择服务器
        total_weight = sum(weights)
        selection_point = self._server_counters[model] % total_weight
        self._server_counters[model] += 1

        # 如果计数太大，重置以避免溢出
        if self._server_counters[model] > 10000:
            self._server_counters[model] = 0

        # 根据权重选择服务器
        cumulative_weight = 0
        for i, weight in enumerate(weights):
            cumulative_weight += weight
            if selection_point < cumulative_weight:
                return healthy_servers[i]

        # 如果权重选择失败，回退到轮询
        return healthy_servers[self._server_counters[model] % len(healthy_servers)]

    def _extract_server_key(self, target: str) -> str:
        """从目标 URL 提取服务器标识（用于熔断器 key）

        使用 netloc (host:port) 作为标识，忽略路径部分。
        例如：https://api.example.com/v1/chat -> api.example.com
        """
        try:
            parsed = urlparse(target)
            return parsed.netloc or target
        except Exception:
            return target

    async def forward_request(
        self, target: str, data: Dict, headers: Dict, stream: bool = False
    ) -> Union[httpx.Response, str]:
        """转发请求到目标服务器

        集成熔断器保护，当上游服务故障时快速失败，防止级联错误。

        Args:
            target: 目标服务器 URL
            data: 请求数据
            headers: 请求头
            stream: 是否为流式请求

        Returns:
            响应数据或流式客户端

        Raises:
            HTTPException: 当熔断器处于 OPEN 状态时抛出 503 错误
        """
        # 提取服务器标识用于熔断器
        server_key = self._extract_server_key(target)

        # 熔断器检查：如果服务器处于熔断状态，快速失败
        if not await self.circuit_breaker.can_execute(server_key):
            logger.warning(f"request blocked | server={server_key} | reason=circuit_open")
            raise HTTPException(
                status_code=503,
                detail=f"Service temporarily unavailable (circuit open for {server_key})"
            )

        # 监控并调整连接池
        await self._monitor_connection_pool()

        # 处理模型名称映射
        if "model" in data and data["model"] in self.app_state.model_name_mapping:
            data = data.copy()
            model_info = self.app_state.model_name_mapping[data["model"]]
            data["model"] = (
                model_info if isinstance(model_info, str) else model_info["name"]
            )

        try:
            if stream:
                stream_client = self.http_client.stream(
                    "POST",
                    target,
                    json=data,
                    headers=headers,
                    timeout=httpx.Timeout(
                        connect=10.0, read=None, write=10.0, pool=10.0
                    ),
                )
                return stream_client

            response = await self.http_client.post(target, json=data, headers=headers)
            response.raise_for_status()

            # 请求成功，更新健康状态和熔断器
            self._update_server_health(target, True)
            await self.circuit_breaker.record_success(server_key)

            return response.text

        except httpx.HTTPStatusError as exc:
            # 服务器错误（5xx）触发熔断记录
            if exc.response.status_code >= 500:
                await self.circuit_breaker.record_failure(server_key, exc)

            self._update_server_health(target, False)
            logger.error(f"upstream error | server={server_key} | status={exc.response.status_code}")

            if stream:
                return exc.response
            return json.dumps({
                "error": f"LLM_SERVER 响应状态码 {exc.response.status_code}",
                "message": str(exc),
            })

        except httpx.RemoteProtocolError as exc:
            # 连接协议错误，记录失败但不重建客户端
            await self.circuit_breaker.record_failure(server_key, exc)
            self._update_server_health(target, False)
            logger.warning(f"connection reset | server={server_key} | error={str(exc)[:50]}")

            if stream:
                raise

            return json.dumps({
                "error": "与 LLM_SERVER 连接已断开，请重试",
                "message": str(exc),
            })

        except httpx.ConnectError as exc:
            # 连接错误（如 DNS 解析失败、连接拒绝等）
            await self.circuit_breaker.record_failure(server_key, exc)
            self._update_server_health(target, False)
            logger.error(f"connection failed | server={server_key}")

            if stream:
                raise HTTPException(
                    status_code=503,
                    detail=f"Failed to connect to upstream server: {server_key}"
                )

            return json.dumps({
                "error": "无法连接到 LLM_SERVER",
                "message": str(exc),
            })

        except httpx.TimeoutException as exc:
            # 请求超时
            await self.circuit_breaker.record_failure(server_key, exc)
            self._update_server_health(target, False)
            logger.error(f"request timeout | server={server_key}")

            if stream:
                raise HTTPException(
                    status_code=504,
                    detail=f"Upstream server timeout: {server_key}"
                )

            return json.dumps({
                "error": "LLM_SERVER 请求超时",
                "message": str(exc),
            })

        except Exception as exc:
            # 其他未知错误
            await self.circuit_breaker.record_failure(server_key, exc)
            self._update_server_health(target, False)
            logger.error(f"unexpected error | server={server_key} | error={str(exc)[:100]}", exc_info=True)

            if stream:
                raise HTTPException(
                    status_code=500,
                    detail=f"Unexpected error: {str(exc)}"
                )

            return json.dumps({
                "error": "与 LLM_SERVER 通信时出现未知错误",
                "message": str(exc),
            })

    def get_auth_header(self, model: str, api_key: str) -> Dict[str, str]:
        """生成认证头

        Args:
            model: 模型名称
            api_key: API密钥

        Returns:
            Dict[str, str]: 认证头
        """
        return {
            "Authorization": f"Bearer {self.app_state.cloud_models.get(model, api_key)}",
            "Content-Type": "application/json",
        }

    def _get_healthy_servers_with_circuit_breaker(self, servers: List[str]) -> List[str]:
        """获取健康且未被熔断的服务器列表

        结合传统的健康检查和熔断器状态来筛选可用服务器。

        Args:
            servers: 候选服务器列表

        Returns:
            可用的服务器列表
        """
        healthy_servers = self._get_healthy_servers(servers)
        available_servers = []

        for server in healthy_servers:
            server_key = self._extract_server_key(server)
            circuit_state = self.circuit_breaker.get_state(server_key)

            # 排除熔断状态的服务器，保留半开状态（允许试探）
            if circuit_state != CircuitState.OPEN:
                available_servers.append(server)
            else:
                logger.debug(f"Server {server_key} is circuit-open, skipping")

        # 如果没有可用服务器，降级返回所有服务器（避免完全不可用）
        return available_servers or servers

    def get_circuit_breaker_stats(self) -> Dict:
        """获取熔断器统计信息（用于监控）

        Returns:
            包含所有熔断器状态的字典
        """
        return {
            "config": self.circuit_breaker.get_config(),
            "circuits": self.circuit_breaker.get_all_stats(),
        }

    async def reset_circuit_breaker(self, server_key: str = None):
        """重置熔断器状态（用于运维操作）

        Args:
            server_key: 要重置的服务器标识，如果为 None 则重置所有
        """
        if server_key:
            await self.circuit_breaker.reset(server_key)
        else:
            await self.circuit_breaker.reset_all()
