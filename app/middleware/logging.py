"""请求追踪中间件

为每个请求生成唯一的 request_id，并在日志中自动关联。
支持从请求头中读取已有的 request_id（用于分布式追踪）。
"""
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
