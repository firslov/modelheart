"""统一日志配置模块

提供结构化、美观的日志系统，支持：
- 统一的日志格式与美观的颜色样式
- 请求追踪 (request_id)
- 模块级别的日志级别控制
- 文件和控制台双输出
- 彩色终端输出
- 日志辅助函数，简化调用
"""
import logging
import sys
from pathlib import Path
from typing import Optional, Any
from contextvars import ContextVar
from datetime import datetime

from app.config.settings import settings

# 请求上下文 - 用于在整个请求生命周期中传递 request_id
_request_context: ContextVar[dict] = ContextVar("_request_context", default={})


class LogStyle:
    """日志样式配置"""

    # ANSI 颜色代码
    COLORS = {
        # 日志级别颜色
        "DEBUG": "\033[90m",      # 暗灰色
        "INFO": "\033[92m",       # 亮绿色
        "WARNING": "\033[93m",    # 亮黄色
        "ERROR": "\033[91m",      # 亮红色
        "CRITICAL": "\033[95m",   # 亮紫色
        # 元素颜色
        "time": "\033[90m",       # 暗灰色
        "module": "\033[36m",     # 青色
        "request_id": "\033[35m", # 紫色
        "location": "\033[33m",   # 黄色
        "key": "\033[34m",        # 蓝色
        "value": "\033[37m",      # 白色
        "success": "\033[92m",    # 亮绿色
        "reset": "\033[0m",       # 重置
        # 强调样式
        "bold": "\033[1m",
        "dim": "\033[2m",
    }

    # 日志级别图标（ASCII 安全，兼容性好）
    ICONS = {
        "DEBUG": "··",
        "INFO": "→",
        "WARNING": "!",
        "ERROR": "×",
        "CRITICAL": "!!",
    }

    # 日志级别显示宽度（用于对齐）
    LEVEL_WIDTH = 7


class ColoredFormatter(logging.Formatter):
    """美观的彩色日志格式化器"""

    def __init__(self, use_colors: bool = True, include_request_id: bool = True):
        """初始化格式化器

        Args:
            use_colors: 是否使用彩色输出
            include_request_id: 是否包含请求ID
        """
        self.use_colors = use_colors
        self.include_request_id = include_request_id
        super().__init__()

    def _colorize(self, text: str, color_key: str) -> str:
        """添加颜色"""
        if not self.use_colors:
            return text
        color = LogStyle.COLORS.get(color_key, "")
        reset = LogStyle.COLORS["reset"]
        return f"{color}{text}{reset}"

    def _format_time(self, record: logging.LogRecord) -> str:
        """格式化时间"""
        time_str = datetime.fromtimestamp(record.created).strftime("%H:%M:%S.%f")[:-3]
        return self._colorize(time_str, "time")

    def _format_level(self, record: logging.LogRecord) -> str:
        """格式化日志级别"""
        level = record.levelname
        icon = LogStyle.ICONS.get(level, "·")
        # 对齐
        padded = f"{icon} {level}".ljust(LogStyle.LEVEL_WIDTH + 2)
        return self._colorize(padded, level)

    def _format_module(self, record: logging.LogRecord) -> str:
        """格式化模块名"""
        if record.name == "root":
            return ""
        # 取模块名最后一部分
        module = record.name.split(".")[-1]
        # 截断过长的模块名
        if len(module) > 12:
            module = module[:10] + ".."
        return self._colorize(f"[{module}]", "module")

    def _format_request_id(self) -> str:
        """格式化请求ID"""
        if not self.include_request_id:
            return ""
        request_id = _request_context.get({}).get("request_id", "")
        if not request_id:
            return ""
        return self._colorize(f"[{request_id[:8]}]", "request_id")

    def _format_location(self, record: logging.LogRecord) -> str:
        """格式化位置信息（仅错误级别）"""
        if record.levelno < logging.ERROR:
            return ""
        location = f"{record.filename}:{record.lineno}"
        return self._colorize(f"[{location}]", "location")

    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录"""
        # 处理消息中的参数
        message = record.getMessage()

        # 构建日志行
        parts = [
            self._format_time(record),
            self._format_level(record),
        ]

        # 添加请求ID
        request_id_part = self._format_request_id()
        if request_id_part:
            parts.append(request_id_part)

        # 添加模块名
        module_part = self._format_module(record)
        if module_part:
            parts.append(module_part)

        # 添加位置信息（错误级别）
        location_part = self._format_location(record)
        if location_part:
            parts.append(location_part)

        # 组合前缀
        prefix = " ".join(parts)

        # 处理多行消息
        if "\n" in message:
            lines = message.split("\n")
            # 第一行正常显示
            result = f"{prefix} {lines[0]}"
            # 后续行缩进对齐
            indent = " " * (len(prefix) + 1)
            for line in lines[1:]:
                result += f"\n{indent}{line}"
            return result

        return f"{prefix} {message}"


class PlainFormatter(logging.Formatter):
    """纯文本格式化器（用于文件输出）"""

    def __init__(self, include_request_id: bool = True):
        self.include_request_id = include_request_id
        super().__init__()

    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录"""
        # 时间戳
        time_str = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        # 日志级别
        level = record.levelname.ljust(8)

        # 构建基础部分
        parts = [f"{time_str} | {level}"]

        # 请求ID
        if self.include_request_id:
            request_id = _request_context.get({}).get("request_id", "")
            if request_id:
                parts.append(f"| {request_id[:8]}")

        # 模块名
        if record.name != "root":
            module = record.name.split(".")[-1]
            parts.append(f"| {module}")

        # 位置信息（错误级别）
        if record.levelno >= logging.ERROR:
            parts.append(f"| {record.filename}:{record.lineno}")

        # 消息
        parts.append(f"| {record.getMessage()}")

        return " ".join(parts)


# ============================================
# 日志辅助函数
# ============================================

def _format_kv(key: str, value: Any) -> str:
    """格式化键值对"""
    if isinstance(value, float):
        value = f"{value:.2f}" if value < 1000 else f"{value:,.0f}"
    elif isinstance(value, int) and value > 1000:
        value = f"{value:,}"
    return f"{key}={value}"


def log_request(logger: logging.Logger, method: str, path: str, **kwargs):
    """记录请求日志

    Args:
        logger: Logger 实例
        method: HTTP 方法
        path: 请求路径
        **kwargs: 附加信息
    """
    parts = [f"{method} {path}"]
    if kwargs:
        parts.append("|")
        parts.append(" ".join(_format_kv(k, v) for k, v in kwargs.items()))
    logger.info(" ".join(parts))


def log_response(logger: logging.Logger, status: int, duration_ms: float, **kwargs):
    """记录响应日志

    Args:
        logger: Logger 实例
        status: HTTP 状态码
        duration_ms: 响应时间（毫秒）
        **kwargs: 附加信息
    """
    parts = [f"← {status}"]
    parts.append(_format_kv("duration", f"{duration_ms:.1f}ms"))
    if kwargs:
        parts.append("|")
        parts.append(" ".join(_format_kv(k, v) for k, v in kwargs.items()))
    logger.info(" ".join(parts))


def log_forward(logger: logging.Logger, model: str, server: str, stream: bool = False):
    """记录请求转发日志

    Args:
        logger: Logger 实例
        model: 模型名称
        server: 目标服务器
        stream: 是否流式
    """
    mode = "stream" if stream else "sync"
    logger.info(f"→ {mode} | model={model} | server={server}")


def log_stream_complete(logger: logging.Logger, model: str, tokens: int = None, duration_ms: float = None):
    """记录流式响应完成日志

    Args:
        logger: Logger 实例
        model: 模型名称
        tokens: token 数量
        duration_ms: 响应时间
    """
    parts = [f"✓ stream | model={model}"]
    if tokens is not None:
        parts.append(f"| tokens={tokens}")
    if duration_ms is not None:
        parts.append(f"| duration={duration_ms:.0f}ms")
    logger.info(" ".join(parts))


def log_error(logger: logging.Logger, message: str, error: Exception = None, **kwargs):
    """记录错误日志

    Args:
        logger: Logger 实例
        message: 错误消息
        error: 异常对象
        **kwargs: 附加上下文
    """
    parts = [message]
    if kwargs:
        parts.append("|")
        parts.append(" ".join(_format_kv(k, v) for k, v in kwargs.items()))
    if error:
        logger.error(" ".join(parts), exc_info=True)
    else:
        logger.error(" ".join(parts))


def log_circuit(logger: logging.Logger, event: str, server: str, **kwargs):
    """记录熔断器事件日志

    Args:
        logger: Logger 实例
        event: 事件类型 (open/close/half_open)
        server: 服务器标识
        **kwargs: 附加信息
    """
    event_icons = {
        "open": "◉ OPEN",
        "close": "○ CLOSE",
        "half_open": "◐ HALF",
        "reset": "↺ RESET",
    }
    icon = event_icons.get(event, event)
    parts = [f"breaker {icon} | server={server}"]
    if kwargs:
        parts.append("|")
        parts.append(" ".join(_format_kv(k, v) for k, v in kwargs.items()))
    logger.warning(" ".join(parts))


# ============================================
# 日志配置
# ============================================

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
        log_file = Path(settings.BASE_DIR) / "logs" / "app.log"
    else:
        log_file = Path(log_file)

    # 确保日志目录存在
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # 是否使用颜色（开发环境 + 终端）
    use_colors = settings.ENV == "development" and sys.stdout.isatty()

    # 创建格式化器
    console_formatter = ColoredFormatter(use_colors=use_colors, include_request_id=include_request_id)
    file_formatter = PlainFormatter(include_request_id=include_request_id)

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # 文件处理器
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(log_level)
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # 设置第三方库的日志级别（减少噪音）
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("multipart").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的 logger

    Args:
        name: logger 名称，通常使用 __name__

    Returns:
        logging.Logger: 配置好的 logger 实例
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
