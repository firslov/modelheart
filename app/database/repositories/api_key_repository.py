"""ApiKey数据访问层

提供ApiKey模型的数据库操作方法。
"""
from typing import Optional, List
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base_repository import BaseRepository
from app.database.models import ApiKey


class ApiKeyRepository(BaseRepository[ApiKey]):
    """ApiKey Repository，提供API密钥相关的数据库操作"""

    async def get_by_api_key(self, api_key: str) -> Optional[ApiKey]:
        """通过API密钥查询记录

        Args:
            api_key: API密钥字符串

        Returns:
            ApiKey对象，不存在时返回None
        """
        result = await self.session.execute(
            select(ApiKey).where(ApiKey.api_key == api_key)
        )
        return result.scalar_one_or_none()

    async def get_by_phone(self, phone: str) -> Optional[ApiKey]:
        """通过手机号查询记录

        Args:
            phone: 手机号

        Returns:
            ApiKey对象，不存在时返回None
        """
        result = await self.session.execute(
            select(ApiKey).where(ApiKey.phone == phone)
        )
        return result.scalar_one_or_none()

    async def get_by_phone_with_usages(self, phone: str) -> Optional[ApiKey]:
        """通过手机号查询记录，预加载 model_usages 关系

        Args:
            phone: 手机号

        Returns:
            ApiKey对象（含model_usages），不存在时返回None
        """
        result = await self.session.execute(
            select(ApiKey)
            .options(selectinload(ApiKey.model_usages))
            .where(ApiKey.phone == phone)
        )
        return result.scalar_one_or_none()

    async def update_usage(self, api_key: str, usage_delta: float) -> bool:
        """原子增量更新usage字段

        使用SQLAlchemy的原子操作，避免并发问题。

        Args:
            api_key: API密钥
            usage_delta: 要增加的使用量

        Returns:
            更新成功返回True，记录不存在返回False
        """
        result = await self.session.execute(
            update(ApiKey)
            .where(ApiKey.api_key == api_key)
            .values(usage=ApiKey.usage + usage_delta)
        )
        return result.rowcount > 0

    async def increment_reqs(self, api_key: str) -> bool:
        """原子增量更新reqs字段

        Args:
            api_key: API密钥

        Returns:
            更新成功返回True，记录不存在返回False
        """
        result = await self.session.execute(
            update(ApiKey)
            .where(ApiKey.api_key == api_key)
            .values(reqs=ApiKey.reqs + 1)
        )
        return result.rowcount > 0

    async def reset_usage(self, api_key: str) -> bool:
        """重置usage和reqs字段

        Args:
            api_key: API密钥

        Returns:
            更新成功返回True，记录不存在返回False
        """
        result = await self.session.execute(
            update(ApiKey)
            .where(ApiKey.api_key == api_key)
            .values(usage=0, reqs=0)
        )
        return result.rowcount > 0

    async def update_limit(self, api_key: str, new_limit: float) -> bool:
        """更新使用限额

        Args:
            api_key: API密钥
            new_limit: 新的限额值

        Returns:
            更新成功返回True，记录不存在返回False
        """
        result = await self.session.execute(
            update(ApiKey)
            .where(ApiKey.api_key == api_key)
            .values(limit_value=new_limit)
        )
        return result.rowcount > 0

    async def delete_by_api_key(self, api_key: str) -> bool:
        """通过API密钥删除记录

        Args:
            api_key: API密钥

        Returns:
            删除成功返回True，记录不存在返回False
        """
        # 先查询获取对象，然后删除（确保级联删除正常工作）
        instance = await self.get_by_api_key(api_key)
        if instance:
            await self.session.delete(instance)
            await self.session.flush()
            return True
        return False

    async def get_all_with_usages(self) -> List[ApiKey]:
        """获取所有API密钥，包含model_usages关系

        Returns:
            ApiKey列表，预加载了model_usages关系
        """
        result = await self.session.execute(
            select(ApiKey).options(selectinload(ApiKey.model_usages))
        )
        return result.scalars().all()

    async def get_all(self) -> List[ApiKey]:
        """获取所有API密钥

        Returns:
            ApiKey列表
        """
        result = await self.session.execute(select(ApiKey))
        return result.scalars().all()

    async def get_for_update(self, api_key: str) -> Optional[ApiKey]:
        """获取记录并加锁（SELECT FOR UPDATE）

        用于防止并发更新竞争条件。

        Args:
            api_key: API密钥

        Returns:
            ApiKey对象，不存在时返回None
        """
        result = await self.session.execute(
            select(ApiKey)
            .where(ApiKey.api_key == api_key)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def update_last_used(self, api_key: str, last_used_str: str) -> bool:
        """更新最后使用时间

        Args:
            api_key: API密钥
            last_used_str: 时间字符串

        Returns:
            更新成功返回True，记录不存在返回False
        """
        from datetime import datetime

        result = await self.session.execute(
            update(ApiKey)
            .where(ApiKey.api_key == api_key)
            .values(last_used=datetime.now(), last_used_str=last_used_str)
        )
        return result.rowcount > 0
