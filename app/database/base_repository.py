"""Repository基类

提供通用的CRUD操作，统一数据访问层。
"""
from abc import ABC, abstractmethod
from typing import TypeVar, Generic, Type, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar('T')


class BaseRepository(Generic[T], ABC):
    """Repository基类，提供通用的数据库操作方法"""

    def __init__(self, session: AsyncSession, model: Type[T]):
        """初始化Repository

        Args:
            session: 数据库会话
            model: ORM模型类
        """
        self.session = session
        self.model = model

    async def get_by_id(self, id: int) -> Optional[T]:
        """通过ID获取记录

        Args:
            id: 记录ID

        Returns:
            记录对象，不存在时返回None
        """
        from sqlalchemy import select

        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> List[T]:
        """获取所有记录

        Returns:
            记录列表
        """
        from sqlalchemy import select

        result = await self.session.execute(select(self.model))
        return result.scalars().all()

    async def create(self, **kwargs) -> T:
        """创建新记录

        Args:
            **kwargs: 模型字段值

        Returns:
            新创建的记录对象
        """
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def update(self, id: int, **kwargs) -> Optional[T]:
        """更新记录

        Args:
            id: 记录ID
            **kwargs: 要更新的字段值

        Returns:
            更新后的记录对象，不存在时返回None
        """
        instance = await self.get_by_id(id)
        if instance:
            for key, value in kwargs.items():
                setattr(instance, key, value)
            await self.session.flush()
        return instance

    async def delete(self, id: int) -> bool:
        """删除记录

        Args:
            id: 记录ID

        Returns:
            删除成功返回True，记录不存在返回False
        """
        instance = await self.get_by_id(id)
        if instance:
            await self.session.delete(instance)
            await self.session.flush()
            return True
        return False

    async def count(self) -> int:
        """获取记录总数

        Returns:
            记录数量
        """
        from sqlalchemy import func, select

        result = await self.session.execute(
            select(func.count()).select_from(self.model)
        )
        return result.scalar()
