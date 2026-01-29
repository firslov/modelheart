"""请求追踪中间件

为每个请求生成唯一的 request_id，并在日志中自动关联。
支持从请求头中读取已有的 request_id（用于分布式追踪）。
"""
import time
import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.utils.logging_config import set_request_context, clear_request_context, get_logger

logger = get_logger(__name__)


class RequestTrackingMiddleware(BaseHTTPMiddleware):
    """请求追踪中间件

    为每个请求生成唯一的 request_id，并：
    1. 设置到日志上下文中，所有日志自动包含 request_id
    2. 添加到响应头中返回给客户端
    3. 支持从请求头中读取已有的 request_id（用于分布式追踪）
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 尝试从请求头获取 request_id（支持分布式追踪）
        request_id = request.headers.get("X-Request-ID") or request.headers.get("X-Trace-ID")

        # 如果没有，生成新的 request_id
        if not request_id:
            request_id = uuid.uuid4().hex

        # 设置请求上下文
        set_request_context(
            request_id=request_id,
            path=request.url.path,
            method=request.method,
        )

        try:
            # 处理请求
            response = await call_next(request)

            # 将 request_id 添加到响应头
            response.headers["X-Request-ID"] = request_id

            return response
        finally:
            # 清除请求上下文
            clear_request_context()


class DetailedRequestLoggingMiddleware(BaseHTTPMiddleware):
    """详细请求日志中间件

    记录每个请求的详细信息，帮助排查问题：
    - 请求方法、路径、客户端IP
    - User-Agent
    - 响应状态码
    - 请求处理时间
    """

    def __init__(self, app: ASGIApp, log_level: str = "INFO"):
        super().__init__(app)
        self.log_level = log_level.upper()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()

        # 获取客户端信息
        client_host = request.client.host if request.client else "unknown"
        client_port = request.client.port if request.client else 0

        # 获取 User-Agent
        user_agent = request.headers.get("user-agent", "unknown")
        referer = request.headers.get("referer", "-")
        authorization = request.headers.get("authorization", "")

        # 构建 authorization 的脱敏显示
        auth_display = "-"
        if authorization:
            parts = authorization.split(" ", 1)
            if len(parts) == 2:
                auth_type, token = parts
                if len(token) > 12:
                    auth_display = f"{auth_type} {token[:8]}...{token[-4:]}"
                else:
                    auth_display = f"{auth_type} ***"
            else:
                auth_display = "***"

        # 记录请求开始
        logger.info(
            f"Request started | {request.method} {request.url.path} | "
            f"client={client_host}:{client_port} | ua=\"{user_agent[:100]}\" | "
            f"auth={auth_display} | referer={referer[:100]}"
        )

        try:
            # 处理请求
            response = await call_next(request)

            # 计算处理时间
            process_time = time.time() - start_time

            # 记录请求完成
            logger.info(
                f"Request completed | {request.method} {request.url.path} | "
                f"status={response.status_code} | duration={process_time:.3f}s"
            )

            return response

        except Exception as e:
            # 计算处理时间
            process_time = time.time() - start_time

            # 记录请求异常
            logger.error(
                f"Request failed | {request.method} {request.url.path} | "
                f"error={type(e).__name__}: {str(e)[:100]} | duration={process_time:.3f}s"
            )
            raise
