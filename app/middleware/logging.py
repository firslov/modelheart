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
    """请求日志中间件

    记录每个请求的关键信息：
    - 请求方法、路径
    - 响应状态码
    - 请求处理时间
    - 客户端IP（用于安全审计）
    """

    def __init__(self, app: ASGIApp, log_level: str = "INFO"):
        super().__init__(app)
        self.log_level = log_level.upper()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()

        # 获取客户端IP（用于安全审计）
        client_host = request.client.host if request.client else "unknown"

        # 只记录 API 请求（静态资源不记录）
        path = request.url.path
        if path.startswith("/static/") or path == "/favicon.ico":
            return await call_next(request)

        try:
            # 处理请求
            response = await call_next(request)

            # 计算处理时间
            process_time = time.time() - start_time

            # 简化日志：只保留关键信息
            logger.info(
                f"{request.method} {path} | {response.status_code} | {process_time:.3f}s | {client_host}"
            )

            return response

        except Exception as e:
            # 计算处理时间
            process_time = time.time() - start_time

            # 收集错误排查关键信息
            error_info = {
                "type": type(e).__name__,
                "message": str(e)[:200] if str(e) else "No message",
            }

            # 根据错误类型添加额外信息
            if hasattr(e, "status_code"):
                error_info["status_code"] = e.status_code

            # 添加请求上下文信息（帮助复现问题）
            context_info = {
                "query_params": dict(request.query_params) if request.query_params else None,
                "content_type": request.headers.get("content-type"),
            }

            # 构建详细错误日志
            log_parts = [
                f"{request.method} {path}",
                f"ERROR",
                f"{process_time:.3f}s",
                f"{client_host}",
                f"{error_info['type']}: {error_info['message']}",
            ]

            # 添加状态码（如果有）
            if "status_code" in error_info:
                log_parts.insert(2, f"status={error_info['status_code']}")

            # 添加上下文（如果有助于排查）
            if context_info["query_params"]:
                log_parts.append(f"query={context_info['query_params']}")

            logger.error(" | ".join(log_parts))
            raise
