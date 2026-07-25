"""请求体大小限制中间件

防止恶意客户端发送超大 payload 耗尽服务端内存。
"""

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from typing import Callable

from app.config.settings import settings


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """限制请求体大小

    通过 Content-Length 头快速检查，大于上限则直接返回 413。
    """

    def __init__(self, app: ASGIApp, max_size: int = None):
        super().__init__(app)
        self.max_size = max_size or settings.MAX_REQUEST_BODY_SIZE

    async def dispatch(self, request: Request, call_next: Callable):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                size = int(content_length)
                if size > self.max_size:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Request body too large. "
                        f"Max: {self.max_size // (1024 * 1024)}MB, "
                        f"Received: {size // (1024 * 1024)}MB",
                    )
            except ValueError:
                pass  # 无效的 content-length，放行让下游处理

        return await call_next(request)
