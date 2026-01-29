"""统一日志配置模块

提供结构化、可配置的日志系统，支持：
- 统一的日志格式
- 请求追踪 (request_id)
- 模块级别的日志级别控制
- 文件和控制台双输出
- 彩色终端输出（开发环境）
"""
import logging
import sys
from pathlib import Path
from typing import Optional
from contextvars import ContextVar
from datetime import datetime

from app.config.settings import settings

# 请求上下文 - 用于在整个请求生命周期中传递 request_id
_request_context: ContextVar[dict] = ContextVar("_request_context", default={})


class RequestFormatter(logging.Formatter):
    """自定义日志格式化器，支持请求上下文"""

    # 颜色代码（开发环境使用）
    COLORS = {
        "DEBUG": "\033[36m",     # 青色
        "INFO": "\033[32m",      # 绿色
        "WARNING": "\033[33m",   # 黄色
        "ERROR": "\033[31m",     # 红色
        "CRITICAL": "\033[35m",  # 紫色
        "RESET": "\033[0m",      # 重置
    }

    def __init__(self, use_colors: bool = False, include_request_id: bool = True):
        """初始化格式化器

        Args:
            use_colors: 是否使用彩色输出（终端环境）
            include_request_id: 是否包含请求ID
        """
        self.use_colors = use_colors and settings.ENV == "development"
        self.include_request_id = include_request_id
        super().__init__()

    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录"""
        # 获取请求ID
        request_id = _request_context.get({}).get("request_id", "-")

        # 构建基础格式
        levelname = record.levelname
        if self.use_colors:
            color = self.COLORS.get(levelname, "")
            reset = self.COLORS["RESET"]
            levelname = f"{color}{levelname}{reset}"

        # 格式: [时间] [级别] [request_id] [模块] 消息
        parts = [
            f"[{datetime.fromtimestamp(record.created).strftime('%H:%M:%S')}]",
            f"[{levelname}]",
        ]

        if self.include_request_id and request_id != "-":
            parts.append(f"[{request_id[:8]}]")

        # 添加模块名（仅非根模块）
        if record.name != "root":
            parts.append(f"[{record.name.split('.')[-1]}]")

        # 添加位置信息（仅ERROR及以上）
        if record.levelno >= logging.ERROR:
            parts.append(f"[{record.filename}:{record.lineno}]")

        parts.append(record.getMessage())

        return " ".join(parts)


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    include_request_id: bool = True,
) -> None:
    """配置应用程序日志

    Args:
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: 日志文件路径（默认为 app.log）
        include_request_id: 是否在日志中包含请求ID
    """
    # 清除现有的处理器
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    # 设置日志级别
    log_level = getattr(logging, level.upper(), logging.INFO)
    root_logger.setLevel(log_level)

    # 日志文件路径
    if log_file is None:
        log_file = Path(settings.BASE_DIR) / "app.log"
    else:
        log_file = Path(log_file)

    # 创建格式化器
    # 文件：不使用颜色，终端：使用颜色
    file_formatter = RequestFormatter(use_colors=False, include_request_id=include_request_id)
    console_formatter = RequestFormatter(use_colors=True, include_request_id=include_request_id)

    # 文件处理器
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(log_level)
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # 设置第三方库的日志级别（减少噪音）
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.WARNING)  # 屏蔽 winch 信号等无关日志
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)  # 保留访问日志
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的logger

    Args:
        name: logger名称，通常使用 __name__

    Returns:
        logging.Logger: 配置好的logger实例
    """
    return logging.getLogger(name)


def set_request_context(request_id: str, **kwargs) -> None:
    """设置请求上下文

    Args:
        request_id: 请求唯一标识
        **kwargs: 其他上下文信息
    """
    _request_context.set({"request_id": request_id, **kwargs})


def get_request_context() -> dict:
    """获取当前请求上下文

    Returns:
        dict: 请求上下文信息
    """
    return _request_context.get({})


def clear_request_context() -> None:
    """清除请求上下文"""
    _request_context.set({})
