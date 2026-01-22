"""ModelUsage数据访问层

提供ModelUsage模型的数据库操作方法。
"""
from typing import Optional, List
from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base_repository import BaseRepository
from app.database.models import ModelUsage


class ModelUsageRepository(BaseRepository[ModelUsage]):
    """ModelUsage Repository，提供模型使用统计相关的数据库操作"""

    async def get_or_create(
        self, api_key_id: int, model_name: str
    ) -> ModelUsage:
        """获取或创建模型使用记录

        如果记录不存在则创建新记录。

        Args:
            api_key_id: API密钥ID
            model_name: 模型名称

        Returns:
            ModelUsage对象
        """
        result = await self.session.execute(
            select(ModelUsage).where(
                and_(
                    ModelUsage.api_key_id == api_key_id,
                    ModelUsage.model_name == model_name,
                )
            )
        )
        usage = result.scalar_one_or_none()

        if not usage:
            usage = ModelUsage(
                api_key_id=api_key_id,
                model_name=model_name,
                requests=0,
                tokens=0
            )
            self.session.add(usage)
            await self.session.flush()

        return usage

    async def increment_usage(
        self,
        api_key_id: int,
        model_name: str,
        request_delta: int = 1,
        token_delta: float = 0,
    ) -> bool:
        """原子增量更新usage统计

        Args:
            api_key_id: API密钥ID
            model_name: 模型名称
            request_delta: 要增加的请求数
            token_delta: 要增加的token数

        Returns:
            更新成功返回True，记录不存在返回False
        """
        result = await self.session.execute(
            update(ModelUsage)
            .where(
                and_(
                    ModelUsage.api_key_id == api_key_id,
                    ModelUsage.model_name == model_name,
                )
            )
            .values(
                requests=ModelUsage.requests + request_delta,
                tokens=ModelUsage.tokens + token_delta,
            )
        )
        return result.rowcount > 0

    async def get_for_update(
        self, api_key_id: int, model_name: str
    ) -> Optional[ModelUsage]:
        """获取记录并加锁（SELECT FOR UPDATE）

        用于防止并发更新竞争条件。

        Args:
            api_key_id: API密钥ID
            model_name: 模型名称

        Returns:
            ModelUsage对象，不存在时返回None
        """
        result = await self.session.execute(
            select(ModelUsage)
            .where(
                and_(
                    ModelUsage.api_key_id == api_key_id,
                    ModelUsage.model_name == model_name,
                )
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_by_api_key_id(self, api_key_id: int) -> List[ModelUsage]:
        """获取指定API密钥的所有模型使用记录

        Args:
            api_key_id: API密钥ID

        Returns:
            ModelUsage列表
        """
        result = await self.session.execute(
            select(ModelUsage).where(ModelUsage.api_key_id == api_key_id)
        )
        return result.scalars().all()

    async def delete_by_api_key_id(self, api_key_id: int) -> int:
        """删除指定API密钥的所有模型使用记录

        Args:
            api_key_id: API密钥ID

        Returns:
            删除的记录数
        """
        from sqlalchemy import delete

        result = await self.session.execute(
            delete(ModelUsage).where(ModelUsage.api_key_id == api_key_id)
        )
        return result.rowcount

    async def reset_all_by_api_key_id(self, api_key_id: int) -> int:
        """重置指定API密钥的所有模型使用统计

        Args:
            api_key_id: API密钥ID

        Returns:
            更新的记录数
        """
        result = await self.session.execute(
            update(ModelUsage)
            .where(ModelUsage.api_key_id == api_key_id)
            .values(requests=0, tokens=0)
        )
        return result.rowcount
