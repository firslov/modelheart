"""队列数据模型 - 用于用量统计队列

此模块定义了队列中使用的数据结构，用于解耦API请求和数据库写入。
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum


class UsageEventType(str, Enum):
    """用量事件类型"""
    UPDATE_USAGE = "update_usage"  # 更新API使用量
    UPDATE_ANTHROPIC_USAGE = "update_anthropic_usage"  # 更新Anthropic使用量
    INCREMENT_MODEL_REQS = "increment_model_reqs"  # 增加模型请求计数


@dataclass
class UsageEventData:
    """用量事件数据

    封装所有需要写入数据库的用量统计信息。
    使用 dataclass 以提高性能和减少内存占用。
    """
    event_type: UsageEventType
    api_key: str
    model: Optional[str] = None
    server_url: Optional[str] = None

    # Token 使用量（从上游响应获取）
    prompt_tokens: int = 0
    completion_tokens: int = 0

    # 权重信息
    input_token_weight: float = 1.0
    output_token_weight: float = 1.0

    # 时间戳（用于调试和监控）
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())

    # 原始请求数据（用于回退计算 token）
    request_data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "event_type": self.event_type,
            "api_key": self.api_key,
            "model": self.model,
            "server_url": self.server_url,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "input_token_weight": self.input_token_weight,
            "output_token_weight": self.output_token_weight,
            "timestamp": self.timestamp,
        }


@dataclass
class QueueStats:
    """队列统计信息"""
    total_enqueued: int = 0  # 总入队数量
    total_flushed: int = 0  # 总刷新数量
    current_queue_size: int = 0  # 当前队列大小
    last_flush_time: Optional[float] = None  # 上次刷新时间
    last_flush_count: int = 0  # 上次刷新数量
    total_errors: int = 0  # 总错误数量
