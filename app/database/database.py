import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config.settings import settings
from app.database.models import Base

# 数据库文件路径 - 使用app/database目录下的数据库
DATABASE_URL = f"sqlite+aiosqlite:///{os.path.join(settings.BASE_DIR, 'app', 'database', 'myapi.db')}"

# 创建异步引擎
# SQLite的aiosqlite驱动不支持连接池参数，需要移除
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # 生产环境设为False
    future=True,
)

# 创建异步会话工厂
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncSession:
    """获取数据库会话"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """初始化数据库，创建所有表"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """关闭数据库连接"""
    await engine.dispose()
