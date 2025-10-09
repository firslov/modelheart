from datetime import timezone, timedelta
from pydantic_settings import BaseSettings
from typing import Dict, Any
import os
import httpx


class Settings(BaseSettings):
    """应用配置类"""

    # 时区设置
    TIMEZONE: timezone = timezone(timedelta(hours=8))

    # 文件路径配置
    BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    STATIC_DIR: str = os.path.join(BASE_DIR, "static")
    TEMPLATES_DIR: str = os.path.join(BASE_DIR, "templates")

    # 应用配置
    CACHE_TTL: int = 600  # 缓存刷新时间(秒)
    DEFAULT_LIMIT: int = 1000000  # 默认API限额(100万token)
    MAX_CONNECTIONS: int = 1000  # 最大连接数
    REQUEST_TIMEOUT: float = 180.0  # 请求超时时间
    READ_TIMEOUT: float = 300.0  # 读取超时时间

    # 环境配置
    ENV: str = os.getenv("ENV", "production")  # 环境: development/production

    # Session配置
    SESSION_SECRET_KEY: str = os.getenv(
        "SESSION_SECRET_KEY", "your-secret-key-here"
    )  # 从环境变量获取密钥
    SESSION_MAX_AGE: int = 3600  # session过期时间(秒)
    SESSION_COOKIE_SECURE: bool = ENV == "production"  # 仅在生产环境使用HTTPS
    SESSION_COOKIE_SAMESITE: str = "lax"  # Cookie SameSite策略

    @property
    def HTTP_CLIENT_CONFIG(self) -> Dict[str, Any]:
        """HTTP客户端配置"""
        return {
            "limits": httpx.Limits(
                max_connections=self.MAX_CONNECTIONS, max_keepalive_connections=100
            ),
            "timeout": httpx.Timeout(
                timeout=self.REQUEST_TIMEOUT, read=self.READ_TIMEOUT
            ),
            "http2": True,
            "transport": httpx.AsyncHTTPTransport(http2=True),
        }

    # 其他
    TOKENIZER_MODEL: str = "gpt-3.5-turbo"  # 默认分词器模型
    HEALTH_CHECK_INTERVAL: int = 60  # 健康检查间隔时间(秒)
    MAX_RETRIES: int = 3  # HTTP请求最大重试次数

    class Config:
        case_sensitive = True


# 创建全局设置实例
settings = Settings()
