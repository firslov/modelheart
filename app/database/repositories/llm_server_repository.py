"""LLMServer和ServerModel数据访问层

提供LLM服务器和服务器模型相关的数据库操作方法。
"""
from typing import Optional, List, Dict
from sqlalchemy import select, update, delete, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base_repository import BaseRepository
from app.database.models import LLMServer, ServerModel


class LLMServerRepository(BaseRepository[LLMServer]):
    """LLMServer Repository，提供LLM服务器相关的数据库操作"""

    async def get_by_url(self, server_url: str) -> Optional[LLMServer]:
        """通过服务器URL查询记录

        Args:
            server_url: 服务器URL

        Returns:
            LLMServer对象，不存在时返回None
        """
        result = await self.session.execute(
            select(LLMServer).where(LLMServer.server_url == server_url)
        )
        return result.scalar_one_or_none()

    async def get_all_with_models(self) -> List[LLMServer]:
        """获取所有服务器，包含models关系

        Returns:
            LLMServer列表，预加载了models关系
        """
        result = await self.session.execute(
            select(LLMServer).options(selectinload(LLMServer.models))
        )
        return result.scalars().all()

    async def get_by_url_with_models(self, server_url: str) -> Optional[LLMServer]:
        """通过URL获取服务器，包含models关系

        Args:
            server_url: 服务器URL

        Returns:
            LLMServer对象，预加载了models关系，不存在时返回None
        """
        result = await self.session.execute(
            select(LLMServer)
            .where(LLMServer.server_url == server_url)
            .options(selectinload(LLMServer.models))
        )
        return result.scalar_one_or_none()

    async def delete_by_url(self, server_url: str) -> bool:
        """通过URL删除服务器

        Args:
            server_url: 服务器URL

        Returns:
            删除成功返回True，记录不存在返回False
        """
        instance = await self.get_by_url(server_url)
        if instance:
            await self.session.delete(instance)
            await self.session.flush()
            return True
        return False

    async def delete_all(self) -> int:
        """删除所有服务器配置

        注意：这将级联删除所有关联的ServerModel记录。

        Returns:
            删除的记录数
        """
        # 先删除所有ServerModel
        await self.session.execute(delete(ServerModel))
        # 再删除所有LLMServer
        result = await self.session.execute(delete(LLMServer))
        return result.rowcount

    async def get_all(self) -> List[LLMServer]:
        """获取所有服务器

        Returns:
            LLMServer列表
        """
        result = await self.session.execute(select(LLMServer))
        return result.scalars().all()


class ServerModelRepository(BaseRepository[ServerModel]):
    """ServerModel Repository，提供服务器模型相关的数据库操作"""

    async def increment_reqs(self, model_id: int) -> bool:
        """原子增量更新reqs字段

        Args:
            model_id: 模型ID

        Returns:
            更新成功返回True，记录不存在返回False
        """
        result = await self.session.execute(
            update(ServerModel)
            .where(ServerModel.id == model_id)
            .values(reqs=ServerModel.reqs + 1)
        )
        return result.rowcount > 0

    async def get_by_frontend_name(self, model_name: str) -> Optional[ServerModel]:
        """通过前端模型名称查询

        支持新旧字段兼容。

        Args:
            model_name: 前端使用的模型名称

        Returns:
            ServerModel对象，不存在时返回None
        """
        result = await self.session.execute(
            select(ServerModel).where(
                or_(
                    ServerModel.actual_model_name == model_name,  # 旧字段
                    ServerModel.frontend_model_name == model_name  # 新字段
                )
            ).options(selectinload(ServerModel.server))
        )
        return result.scalar_one_or_none()

    async def get_by_server_and_frontend_name(
        self, server_id: int, model_name: str
    ) -> Optional[ServerModel]:
        """通过服务器ID和前端模型名称查询

        Args:
            server_id: 服务器ID
            model_name: 前端使用的模型名称

        Returns:
            ServerModel对象，不存在时返回None
        """
        result = await self.session.execute(
            select(ServerModel).where(
                ServerModel.server_id == server_id,
                or_(
                    ServerModel.actual_model_name == model_name,  # 旧字段
                    ServerModel.frontend_model_name == model_name  # 新字段
                )
            )
        )
        return result.scalar_one_or_none()

    async def find_by_server_url_and_model(
        self, server_url: str, model_name: str, session: AsyncSession
    ) -> Optional[ServerModel]:
        """通过服务器URL和前端模型名称查找模型

        Args:
            server_url: 服务器URL
            model_name: 前端使用的模型名称
            session: 数据库会话

        Returns:
            ServerModel对象，不存在时返回None
        """
        # 先获取服务器
        result = await session.execute(
            select(LLMServer)
            .where(LLMServer.server_url == server_url)
            .options(selectinload(LLMServer.models))
        )
        server = result.scalar_one_or_none()

        if not server:
            return None

        # 在服务器的模型中查找
        for server_model in server.models:
            frontend_name = (
                server_model.frontend_model_name or server_model.actual_model_name
            )
            if frontend_name == model_name:
                return server_model

        return None

    async def delete_by_server_id(self, server_id: int) -> int:
        """删除指定服务器的所有模型

        Args:
            server_id: 服务器ID

        Returns:
            删除的记录数
        """
        result = await self.session.execute(
            delete(ServerModel).where(ServerModel.server_id == server_id)
        )
        return result.rowcount
