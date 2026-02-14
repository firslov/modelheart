"""用量统计队列服务

通过内存队列 + 后台工作器模式，解耦API请求和数据库写入：
1. API请求结束时将用量数据入队（非阻塞）
2. 后台工作器批量收集数据并定时刷新到数据库
3. 优雅关闭时确保所有数据都被写入

性能提升：
- 流式响应不再阻塞等待数据库写入
- 批量写入减少数据库操作次数
- 数据库连接复用率提升
"""
import asyncio
from collections import defaultdict
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

from app.models.queue_models import (
    UsageEventData,
    UsageEventType,
    QueueStats,
)
from app.database.database import AsyncSessionLocal
from app.database.models import ApiKey, ModelUsage, LLMServer
from app.database.repositories import (
    ApiKeyRepository,
    ModelUsageRepository,
    LLMServerRepository,
)
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from app.utils.logging_config import get_logger

logger = get_logger(__name__)


class UsageQueue:
    """用量统计队列服务

    工作流程：
    1. API请求通过 enqueue() 将用量数据放入队列
    2. 后台工作器 _worker() 持续从队列取数据
    3. 达到 batch_size 或 flush_interval 时触发批量写入
    4. 应用关闭时调用 stop_worker() 确保数据全部写入
    """

    def __init__(
        self,
        batch_size: int = 100,
        flush_interval: float = 5.0,
    ):
        """初始化队列服务

        Args:
            batch_size: 批量写入大小，达到此数量时立即刷新
            flush_interval: 刷新间隔（秒），超过此时间时触发刷新
        """
        self.queue: asyncio.Queue[UsageEventData] = asyncio.Queue()
        self.batch: List[UsageEventData] = []
        self.batch_size = batch_size
        self.flush_interval = flush_interval

        # 工作器控制
        self._worker_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._started = False

        # 统计信息
        self.stats = QueueStats()

        # 按事件类型分组的缓冲区（优化批量写入）
        self._grouped_buffer: Dict[UsageEventType, List[UsageEventData]] = defaultdict(
            list
        )

    async def enqueue(self, event_data: UsageEventData) -> None:
        """入队用量事件数据

        非阻塞操作，立即返回。

        Args:
            event_data: 用量事件数据
        """
        await self.queue.put(event_data)
        self.stats.total_enqueued += 1

    async def start_worker(self) -> None:
        """启动后台工作器

        应在应用启动时调用。
        """
        if self._started:
            logger.warning("UsageQueue already running")
            return

        self._started = True
        self._stop_event.clear()
        self._worker_task = asyncio.create_task(self._worker())
        logger.info(f"UsageQueue started | batch={self.batch_size} | interval={self.flush_interval}s")

    async def stop_worker(self) -> None:
        """停止工作器并刷新剩余数据

        应在应用关闭时调用。会阻塞直到所有数据都被写入。
        """
        if not self._started:
            return

        logger.info("UsageQueue stopping...")

        # 发送停止信号
        self._stop_event.set()

        # 取消工作器任务
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        # 刷新剩余数据
        if self._grouped_buffer:
            remaining = sum(len(v) for v in self._grouped_buffer.values())
            logger.info(f"UsageQueue flush | remaining={remaining}")
            await self._flush_to_database()

        self._started = False
        logger.info("UsageQueue stopped")

    async def _worker(self) -> None:
        """后台工作器协程

        持续从队列取数据并按事件类型分组，达到条件时触发批量写入。
        """
        last_flush = asyncio.get_event_loop().time()

        while not self._stop_event.is_set():
            try:
                # 使用 timeout 确保定期检查 flush_interval
                event_data = await asyncio.wait_for(
                    self.queue.get(), timeout=self.flush_interval
                )

                # 按事件类型分组
                self._grouped_buffer[event_data.event_type].append(event_data)
                self.stats.current_queue_size = self.queue.qsize()

                # 检查是否需要刷新
                total_buffered = sum(len(v) for v in self._grouped_buffer.values())
                current_time = asyncio.get_event_loop().time()
                elapsed = current_time - last_flush

                if total_buffered >= self.batch_size or elapsed >= self.flush_interval:
                    await self._flush_to_database()
                    last_flush = current_time

            except asyncio.TimeoutError:
                # 超时触发刷新
                total_buffered = sum(len(v) for v in self._grouped_buffer.values())
                if total_buffered > 0:
                    await self._flush_to_database()
                    last_flush = asyncio.get_event_loop().time()

            except Exception as e:
                logger.error(f"worker error | error={str(e)[:100]}", exc_info=True)
                self.stats.total_errors += 1
                # 继续运行，不因错误停止

    async def _flush_to_database(self) -> None:
        """批量刷新到数据库

        将缓冲区中的数据按事件类型分组后批量写入数据库。
        """
        if not self._grouped_buffer:
            return

        start_time = asyncio.get_event_loop().time()
        total_events = sum(len(v) for v in self._grouped_buffer.values())

        try:
            async with AsyncSessionLocal() as session:
                # 处理 UPDATE_USAGE 事件
                if UsageEventType.UPDATE_USAGE in self._grouped_buffer:
                    await self._process_update_usage(
                        session, self._grouped_buffer[UsageEventType.UPDATE_USAGE]
                    )

                # 处理 UPDATE_ANTHROPIC_USAGE 事件
                if UsageEventType.UPDATE_ANTHROPIC_USAGE in self._grouped_buffer:
                    await self._process_update_anthropic_usage(
                        session,
                        self._grouped_buffer[UsageEventType.UPDATE_ANTHROPIC_USAGE],
                    )

                # 处理 INCREMENT_MODEL_REQS 事件
                if UsageEventType.INCREMENT_MODEL_REQS in self._grouped_buffer:
                    await self._process_increment_model_reqs(
                        session,
                        self._grouped_buffer[UsageEventType.INCREMENT_MODEL_REQS],
                    )

                await session.commit()

            # 更新统计
            self.stats.total_flushed += total_events
            self.stats.last_flush_count = total_events
            self.stats.last_flush_time = start_time

            elapsed = asyncio.get_event_loop().time() - start_time
            # 仅在调试模式或异常情况下记录
            rate = total_events / elapsed
            if rate < 100 or elapsed > 1.0:
                logger.warning(f"flush slow | events={total_events} | duration={elapsed:.3f}s | rate={rate:.0f}/s")
            else:
                logger.debug(f"flush ok | events={total_events} | duration={elapsed:.3f}s | rate={rate:.0f}/s")

            # 清空缓冲区
            self._grouped_buffer.clear()

        except Exception as e:
            logger.error(f"flush failed | events={total_events} | error={str(e)[:100]}", exc_info=True)
            self.stats.total_errors += 1
            # 注意：数据保留在缓冲区中，下次重试

    async def _process_update_usage(
        self, session: AsyncSessionLocal, events: List[UsageEventData]
    ) -> None:
        """批量处理 UPDATE_USAGE 事件

        优化策略：
        1. 按 api_key 分组，聚合同一 API key 的所有更新
        2. 使用 SELECT FOR UPDATE 防止并发问题
        """
        # 创建Repository实例
        api_key_repo = ApiKeyRepository(session, ApiKey)
        model_usage_repo = ModelUsageRepository(session, ModelUsage)

        # 按 api_key 分组
        grouped_by_key: Dict[str, List[UsageEventData]] = defaultdict(list)
        for event in events:
            grouped_by_key[event.api_key].append(event)

        for api_key, key_events in grouped_by_key.items():
            # 锁定 API key 记录
            api_key_record = await api_key_repo.get_for_update(api_key)

            if not api_key_record:
                continue

            # 更新基本字段
            total_weighted_tokens = 0
            api_key_record.reqs += len(key_events)
            api_key_record.last_used = datetime.now()
            api_key_record.last_used_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 按模型分组处理
            model_updates: Dict[str, Dict[str, float]] = defaultdict(
                lambda: {"tokens": 0, "requests": 0}
            )

            for event in key_events:
                # 计算加权 token
                weighted = (
                    event.prompt_tokens * event.input_token_weight
                    + event.completion_tokens * event.output_token_weight
                )
                total_weighted_tokens += weighted

                if event.model:
                    model_updates[event.model]["tokens"] += weighted
                    model_updates[event.model]["requests"] += 1

            api_key_record.usage += total_weighted_tokens

            # 更新模型使用统计
            for model_name, model_data in model_updates.items():
                model_usage = await model_usage_repo.get_for_update(api_key_record.id, model_name)

                if not model_usage:
                    model_usage = ModelUsage(
                        api_key_id=api_key_record.id,
                        model_name=model_name,
                        requests=model_data["requests"],
                        tokens=model_data["tokens"],
                    )
                    session.add(model_usage)
                else:
                    model_usage.requests += model_data["requests"]
                    model_usage.tokens += model_data["tokens"]

    async def _process_update_anthropic_usage(
        self, session: AsyncSessionLocal, events: List[UsageEventData]
    ) -> None:
        """批量处理 UPDATE_ANTHROPIC_USAGE 事件

        Anthropic 接口不计算 token 用量，只增加请求计数。
        """
        # 创建Repository实例
        api_key_repo = ApiKeyRepository(session, ApiKey)
        model_usage_repo = ModelUsageRepository(session, ModelUsage)

        # 按 api_key 分组
        grouped_by_key: Dict[str, List[UsageEventData]] = defaultdict(list)
        for event in events:
            grouped_by_key[event.api_key].append(event)

        for api_key, key_events in grouped_by_key.items():
            api_key_record = await api_key_repo.get_for_update(api_key)

            if not api_key_record:
                continue

            # 只更新请求计数和时间
            api_key_record.reqs += len(key_events)
            api_key_record.last_used = datetime.now()
            api_key_record.last_used_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 按模型更新统计
            model_requests: Dict[str, int] = defaultdict(int)
            for event in key_events:
                if event.model:
                    model_requests[event.model] += 1

            for model_name, request_count in model_requests.items():
                model_usage = await model_usage_repo.get_for_update(api_key_record.id, model_name)

                if not model_usage:
                    model_usage = ModelUsage(
                        api_key_id=api_key_record.id,
                        model_name=model_name,
                        requests=request_count,
                        tokens=0,  # Anthropic 不计算 token
                    )
                    session.add(model_usage)
                else:
                    model_usage.requests += request_count

    async def _process_increment_model_reqs(
        self, session: AsyncSessionLocal, events: List[UsageEventData]
    ) -> None:
        """批量处理 INCREMENT_MODEL_REQS 事件

        更新服务器的模型请求计数。
        优化：先批量加载所有服务器，避免重复查询。
        """
        # 创建Repository实例
        llm_server_repo = LLMServerRepository(session, LLMServer)

        # 按 server_url + model 分组
        grouped: Dict[tuple, int] = defaultdict(int)
        for event in events:
            if event.server_url and event.model:
                grouped[(event.server_url, event.model)] += 1

        if not grouped:
            return

        # 批量加载所有需要的服务器（优化：一次查询获取所有服务器）
        server_urls = set(server_url for (server_url, _) in grouped.keys())

        # 一次性获取所有服务器
        all_servers = await llm_server_repo.get_all_with_models()
        server_map = {server.server_url: server for server in all_servers}

        # 更新模型请求计数
        for (server_url, model_name), count in grouped.items():
            server = server_map.get(server_url)

            if server:
                for server_model in server.models:
                    frontend_name = (
                        server_model.frontend_model_name
                        or server_model.actual_model_name
                    )
                    if frontend_name == model_name:
                        server_model.reqs += count
                        break

    def get_stats(self) -> Dict[str, Any]:
        """获取队列统计信息"""
        return {
            "total_enqueued": self.stats.total_enqueued,
            "total_flushed": self.stats.total_flushed,
            "current_queue_size": self.queue.qsize(),
            "current_buffer_size": sum(len(v) for v in self._grouped_buffer.values()),
            "last_flush_time": self.stats.last_flush_time,
            "last_flush_count": self.stats.last_flush_count,
            "total_errors": self.stats.total_errors,
            "started": self._started,
        }
