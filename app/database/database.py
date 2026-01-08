import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config.settings import settings
from app.database.models import Base

# 数据库文件路径 - 使用app/database目录下的数据库
DATABASE_URL = f"sqlite+aiosqlite:///{os.path.join(settings.BASE_DIR, 'app', 'database', 'myapi.db')}"

# 创建异步引擎
# SQLite连接池配置：
# - pool_pre_ping: 连接健康检查，防止使用失效连接
# - pool_recycle: 连接回收时间，避免长时间持有连接
# - connect_args: SQLite特定配置
# 注意：将来迁移到PostgreSQL时，可以添加pool_size和max_overflow参数
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # 生产环境设为False
    future=True,
    pool_pre_ping=True,  # 连接健康检查，每次使用前验证连接有效性
    pool_recycle=3600,  # 1小时后回收连接，防止连接长时间闲置
    connect_args={
        "check_same_thread": False,  # 允许多线程访问（FastAPI异步场景需要）
    },
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
