import asyncio
import signal
import sys
from contextlib import asynccontextmanager
from typing import Set

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.models.api_models import ApiKeyUsage
from app.services.api_service import ApiService
from app.services.llm_service import LLMService
from app.services.usage_queue import UsageQueue
from app.utils.logging_config import get_logger
from app.middleware.logging import RequestTrackingMiddleware, DetailedRequestLoggingMiddleware
from app.database.database import get_db_session, init_db

logger = get_logger(__name__)


class Application:
    """应用程序核心类，负责管理应用的生命周期和核心服务"""

    def __init__(self):
        self.llm_service = LLMService()
        self.api_service = ApiService()
        self.usage_queue = UsageQueue(
            batch_size=100,  # 批量写入大小
            flush_interval=5.0,  # 5秒刷新间隔
        )
        self.background_tasks: Set[asyncio.Task] = set()

    async def startup(self) -> None:
        """应用启动初始化"""
        # 初始化数据库
        await init_db()

        # 初始化服务
        await self.llm_service.initialize()

        # 从数据库加载LLM服务器配置
        from app.database.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await self.llm_service.init_llm_resources_from_db(session)

        # 启动用量队列工作器
        await self.usage_queue.start_worker()

        # 启动后台任务
        self._start_background_tasks()

    async def shutdown(self) -> None:
        """应用关闭清理"""
        # 停止用量队列工作器（会等待所有数据写入完成）
        await self.usage_queue.stop_worker()

        # 取消后台任务
        for task in self.background_tasks:
            task.cancel()

        # 等待任务完成
        if self.background_tasks:
            await asyncio.gather(*self.background_tasks, return_exceptions=True)

        # 清理资源
        await self.llm_service.cleanup()

    def _start_background_tasks(self) -> None:
        """启动后台任务"""
        task = self._periodic_health_check_task()
        bg_task = asyncio.create_task(task)
        self.background_tasks.add(bg_task)
        bg_task.add_done_callback(self.background_tasks.discard)

    async def _periodic_health_check_task(self) -> None:
        """定期刷新LLM服务器配置任务"""
        while True:
            await asyncio.sleep(settings.CACHE_TTL)

            # 定期刷新LLM服务器配置
            async for session in get_db_session():
                await self.llm_service.init_llm_resources_from_db(session)
                break

            logger.debug("LLM servers config refreshed")


def create_application() -> FastAPI:
    """创建FastAPI应用实例"""
    app = Application()

    @asynccontextmanager
    async def lifespan(fastapi_app: FastAPI):
        # 启动
        await app.startup()
        yield
        # 关闭
        await app.shutdown()

    # 创建FastAPI应用
    fastapi_app = FastAPI(lifespan=lifespan)

    # 配置中间件
    # CORS 中间件必须最先添加（用于处理预检请求）
    # 注意：allow_credentials=True 时不能使用 "*"，必须指定具体 origin
    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    # 添加请求追踪中间件
    fastapi_app.add_middleware(RequestTrackingMiddleware)

    # 添加详细请求日志中间件（用于排查问题）
    fastapi_app.add_middleware(DetailedRequestLoggingMiddleware)

    # 注意：TrustedHostMiddleware 已禁用，因为它会导致 "Invalid host header" 错误
    # 如果需要启用，请取消下面的注释并配置正确的 allowed_hosts
    # if settings.ENV == "production":
    #     fastapi_app.add_middleware(
    #         TrustedHostMiddleware,
    #         allowed_hosts=["*"],  # 或指定具体的域名列表
    #     )

    # 配置静态文件和模板
    fastapi_app.mount(
        "/static", StaticFiles(directory=settings.STATIC_DIR), name="static"
    )

    # 注册信号处理
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))

    # 保存应用实例
    fastapi_app.state.app = app

    return fastapi_app
