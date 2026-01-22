"""Repository依赖注入工厂

提供FastAPI依赖注入函数，用于在路由中获取Repository实例。
"""
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database import get_db_session
from app.database.models import ApiKey, LLMServer, ServerModel, ModelUsage
from app.database.repositories.api_key_repository import ApiKeyRepository
from app.database.repositories.llm_server_repository import (
    LLMServerRepository,
    ServerModelRepository,
)
from app.database.repositories.model_usage_repository import ModelUsageRepository


async def get_api_key_repo(
    session: AsyncSession = Depends(get_db_session),
) -> ApiKeyRepository:
    """获取ApiKeyRepository实例

    Args:
        session: 数据库会话

    Returns:
        ApiKeyRepository实例
    """
    return ApiKeyRepository(session, ApiKey)


async def get_llm_server_repo(
    session: AsyncSession = Depends(get_db_session),
) -> LLMServerRepository:
    """获取LLMServerRepository实例

    Args:
        session: 数据库会话

    Returns:
        LLMServerRepository实例
    """
    return LLMServerRepository(session, LLMServer)


async def get_server_model_repo(
    session: AsyncSession = Depends(get_db_session),
) -> ServerModelRepository:
    """获取ServerModelRepository实例

    Args:
        session: 数据库会话

    Returns:
        ServerModelRepository实例
    """
    return ServerModelRepository(session, ServerModel)


async def get_model_usage_repo(
    session: AsyncSession = Depends(get_db_session),
) -> ModelUsageRepository:
    """获取ModelUsageRepository实例

    Args:
        session: 数据库会话

    Returns:
        ModelUsageRepository实例
    """
    return ModelUsageRepository(session, ModelUsage)


# 导出所有Repository类，方便直接使用
__all__ = [
    "get_api_key_repo",
    "get_llm_server_repo",
    "get_server_model_repo",
    "get_model_usage_repo",
    "ApiKeyRepository",
    "LLMServerRepository",
    "ServerModelRepository",
    "ModelUsageRepository",
]
