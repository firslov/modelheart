import json
from typing import Dict, Optional, Union, List
from collections import defaultdict
import time
import socket

import httpx
from fastapi import HTTPException

from app.config.settings import settings
from app.models.api_models import AppState
from app.utils.helpers import logger


class LLMService:
    """LLM服务管理类"""

    def __init__(self):
        self.http_client: Optional[httpx.AsyncClient] = None
        self.app_state = AppState()
        self._server_health = defaultdict(lambda: {"healthy": True, "last_check": 0})
        self._server_counters = defaultdict(int)

    async def initialize(self) -> None:
        """初始化HTTP客户端"""
        self.http_client = httpx.AsyncClient(
            limits=httpx.Limits(
                max_connections=1000,
                max_keepalive_connections=100,
                keepalive_expiry=300,
            ),
            timeout=httpx.Timeout(
                connect=10.0,  # 连接超时10秒
                read=300.0,  # 读取超时300秒
                write=10.0,  # 写入超时10秒
                pool=10.0,  # 连接池超时10秒
            ),
            transport=httpx.AsyncHTTPTransport(
                retries=3,  # 自动重试3次
                http2=True,  # 启用HTTP/2
                socket_options=[
                    (socket.IPPROTO_TCP, socket.TCP_NODELAY, 1),
                    (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
                ],
            ),
        )
        self._connection_pool_stats = {
            "last_check": time.time(),
            "active_connections": 0,
            "max_connections": 1000,
            "adjustment_interval": 60,  # 每60秒检查一次
        }
        # logger.info("HTTP client initialized with optimized settings")

    async def _monitor_connection_pool(self) -> None:
        """监控并动态调整连接池"""
        current_time = time.time()
        if (
            current_time - self._connection_pool_stats["last_check"]
            > self._connection_pool_stats["adjustment_interval"]
        ):
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

            self._connection_pool_stats["last_check"] = current_time

    async def cleanup(self) -> None:
        """清理资源"""
        if self.http_client:
            await self.http_client.aclose()

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

        healthy_servers = self._get_healthy_servers(servers)

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

    async def forward_request(
        self, target: str, data: Dict, headers: Dict, stream: bool = False
    ) -> Union[httpx.Response, str]:
        """转发请求到目标服务器，如果model有映射关系，则使用映射后的模型名"""
        # 监控并调整连接池
        await self._monitor_connection_pool()

        if "model" in data and data["model"] in self.app_state.model_name_mapping:
            data = data.copy()
            model_info = self.app_state.model_name_mapping[data["model"]]
            # 处理新旧格式兼容：如果是字符串直接使用，如果是对象则取name字段
            data["model"] = (
                model_info if isinstance(model_info, str) else model_info["name"]
            )

        # # 打印转发请求详情
        # logger.info(f"Forwarding request to: {target}")
        # logger.info(f"Request headers: {json.dumps(headers, indent=2)}")
        # logger.info(f"Request body: {json.dumps(data, indent=2)}")

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
            self._update_server_health(target, True)
            return response.text

        except httpx.HTTPStatusError as exc:
            self._update_server_health(target, False)
            logger.error(f"HTTP error for {target}: {exc.response.status_code}")

            # 仅重置问题连接
            if self.http_client:
                await self.http_client.aclose(force=False)
                self.http_client = httpx.AsyncClient(
                    limits=httpx.Limits(
                        max_connections=1000,
                        max_keepalive_connections=100,
                        keepalive_expiry=300,
                    ),
                    timeout=httpx.Timeout(
                        connect=10.0, read=300.0, write=10.0, pool=10.0
                    ),
                    transport=httpx.AsyncHTTPTransport(
                        retries=3,
                        http2=True,
                        socket_options=[
                            (socket.IPPROTO_TCP, socket.TCP_NODELAY, 1),
                            (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
                        ],
                    ),
                )

            if stream:
                return exc.response
            return json.dumps(
                {
                    "error": f"LLM_SERVER 响应状态码 {exc.response.status_code}",
                    "message": str(exc),
                }
            )

        except Exception as exc:
            self._update_server_health(target, False)
            logger.error(f"Network error for {target}: {str(exc)}")

            if self.http_client:
                await self.http_client.aclose(force=False)
                self.http_client = httpx.AsyncClient(
                    limits=httpx.Limits(
                        max_connections=1000,
                        max_keepalive_connections=100,
                        keepalive_expiry=300,
                    ),
                    timeout=httpx.Timeout(
                        connect=10.0, read=300.0, write=10.0, pool=10.0
                    ),
                    transport=httpx.AsyncHTTPTransport(
                        retries=3,
                        http2=True,
                        socket_options=[
                            (socket.IPPROTO_TCP, socket.TCP_NODELAY, 1),
                            (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
                        ],
                    ),
                )

            if stream:
                return httpx.Response(status_code=500, text=str(exc))
            return json.dumps(
                {"error": "与 LLM_SERVER 通信时出现网络错误", "message": str(exc)}
            )

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
