# Model Heart 项目重构需求

## 目标

1. **路由模块拆分** - 将 `app/api/routes.py` (1089行) 按功能拆分为多个模块
2. **数据库操作统一** - 引入 Repository 模式，统一数据访问层
3. **API速率限制** - 使用 slowapi 实现请求频率控制

---

## 1. 路由模块拆分

### 当前结构
```
app/api/routes.py  # 1089行，所有路由集中在一个文件
```

### 目标结构
```
app/api/
├── __init__.py          # 路由聚合入口，导出 router
├── user.py              # 用户注册、查询额度
├── admin.py             # 管理员登录、用户管理、仪表盘
├── llm.py               # LLM转发接口（chat/completions/embeddings/anthropic）
└── server.py            # 服务器配置管理
```

### 模块职责划分

| 文件 | 端点 |
|------|------|
| `user.py` | `GET /`, `POST /generate-api-key`, `POST /check-usage` |
| `admin.py` | `GET /login`, `POST /login`, `GET /logout`, `GET /dashboard`, `POST /update-api-key-limit`, `POST /reset-api-key-usage`, `POST /revoke-api-key`, `POST /change-user-password` |
| `llm.py` | `GET /models`, `GET /get-models`, `POST /v1/chat/completions`, `POST /v1/completions`, `POST /v1/embeddings`, `POST /anthropic/v1/messages` |
| `server.py` | `GET /get-llm-servers`, `POST /update-llm-servers` |

### `__init__.py` 路由聚合
```python
from fastapi import APIRouter
from app.api.user import router as user_router
from app.api.admin import router as admin_router
from app.api.llm import router as llm_router
from app.api.server import router as server_router

router = APIRouter()
router.include_router(user_router)
router.include_router(admin_router)
router.include_router(llm_router)
router.include_router(server_router)
```

---

## 2. 数据库操作统一

### 当前问题
```python
# ORM 与原生 SQL 混用
await session.execute(text("UPDATE api_keys SET limit_value = :limit ..."))
result = await session.execute(select(ApiKey).where(ApiKey.phone == phone))
```

### 目标结构
```
app/database/
├── database.py              # 保持不变
├── models.py                # 保持不变
├── base_repository.py       # 新增：Repository 基类
└── repositories/
    ├── __init__.py
    ├── api_key_repository.py
    ├── llm_server_repository.py
    └── model_usage_repository.py
```

### `base_repository.py`
```python
from abc import ABC, abstractmethod
from typing import TypeVar, Generic, Type, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar('T')

class BaseRepository(Generic[T], ABC):
    def __init__(self, session: AsyncSession, model: Type[T]):
        self.session = session
        self.model = model

    async def get_by_id(self, id: int) -> Optional[T]:
        from sqlalchemy import select
        result = await self.session.execute(select(self.model).where(self.model.id == id))
        return result.scalar_one_or_none()

    async def get_all(self) -> List[T]:
        from sqlalchemy import select
        result = await self.session.execute(select(self.model))
        return result.scalars().all()

    async def create(self, **kwargs) -> T:
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def update(self, id: int, **kwargs) -> Optional[T]:
        instance = await self.get_by_id(id)
        if instance:
            for key, value in kwargs.items():
                setattr(instance, key, value)
            await self.session.flush()
        return instance

    async def delete(self, id: int) -> bool:
        instance = await self.get_by_id(id)
        if instance:
            await self.session.delete(instance)
            await self.session.flush()
            return True
        return False
```

### `api_key_repository.py`
```python
from sqlalchemy import select, update
from app.database.base_repository import BaseRepository
from app.database.models import ApiKey

class ApiKeyRepository(BaseRepository[ApiKey]):
    async def get_by_api_key(self, api_key: str) -> Optional[ApiKey]:
        result = await self.session.execute(
            select(ApiKey).where(ApiKey.api_key == api_key)
        )
        return result.scalar_one_or_none()

    async def get_by_phone(self, phone: str) -> Optional[ApiKey]:
        result = await self.session.execute(
            select(ApiKey).where(ApiKey.phone == phone)
        )
        return result.scalar_one_or_none()

    async def update_usage(self, api_key: str, usage_delta: float) -> bool:
        result = await self.session.execute(
            update(ApiKey)
            .where(ApiKey.api_key == api_key)
            .values(usage=ApiKey.usage + usage_delta)
        )
        return result.rowcount > 0

    async def increment_reqs(self, api_key: str) -> bool:
        result = await self.session.execute(
            update(ApiKey)
            .where(ApiKey.api_key == api_key)
            .values(reqs=ApiKey.reqs + 1)
        )
        return result.rowcount > 0

    async def reset_usage(self, api_key: str) -> bool:
        result = await self.session.execute(
            update(ApiKey)
            .where(ApiKey.api_key == api_key)
            .values(usage=0, reqs=0)
        )
        return result.rowcount > 0

    async def update_limit(self, api_key: str, new_limit: float) -> bool:
        result = await self.session.execute(
            update(ApiKey)
            .where(ApiKey.api_key == api_key)
            .values(limit_value=new_limit)
        )
        return result.rowcount > 0

    async def delete_by_api_key(self, api_key: str) -> bool:
        result = await self.session.execute(
            update(ApiKey).where(ApiKey.api_key == api_key)
        )
        if instance := result.scalar_one_or_none():
            await self.session.delete(instance)
            return True
        return False
```

### `llm_server_repository.py`
```python
from sqlalchemy import select
from app.database.base_repository import BaseRepository
from app.database.models import LLMServer, ServerModel

class LLMServerRepository(BaseRepository[LLMServer]):
    async def get_by_url(self, server_url: str) -> Optional[LLMServer]:
        result = await self.session.execute(
            select(LLMServer).where(LLMServer.server_url == server_url)
        )
        return result.scalar_one_or_none()

    async def get_all_with_models(self) -> list[LLMServer]:
        from sqlalchemy.orm import selectinload
        result = await self.session.execute(
            select(LLMServer)
            .options(selectinload(LLMServer.models))
        )
        return result.scalars().all()

    async def delete_by_url(self, server_url: str) -> bool:
        instance = await self.get_by_url(server_url)
        if instance:
            await self.session.delete(instance)
            await self.session.flush()
            return True
        return False

class ServerModelRepository(BaseRepository[ServerModel]):
    async def increment_reqs(self, model_id: int) -> bool:
        from sqlalchemy import update
        result = await self.session.execute(
            update(ServerModel)
            .where(ServerModel.id == model_id)
            .values(reqs=ServerModel.reqs + 1)
        )
        return result.rowcount > 0
```

### `model_usage_repository.py`
```python
from sqlalchemy import select
from app.database.base_repository import BaseRepository
from app.database.models import ModelUsage

class ModelUsageRepository(BaseRepository[ModelUsage]):
    async def get_or_create(self, api_key_id: int, model_name: str) -> ModelUsage:
        result = await self.session.execute(
            select(ModelUsage).where(
                ModelUsage.api_key_id == api_key_id,
                ModelUsage.model_name == model_name
            )
        )
        usage = result.scalar_one_or_none()
        if not usage:
            usage = ModelUsage(api_key_id=api_key_id, model_name=model_name)
            self.session.add(usage)
            await self.session.flush()
        return usage

    async def increment_usage(
        self,
        api_key_id: int,
        model_name: str,
        request_tokens: float,
        completion_tokens: float
    ) -> bool:
        from sqlalchemy import update
        result = await self.session.execute(
            update(ModelUsage)
            .where(
                ModelUsage.api_key_id == api_key_id,
                ModelUsage.model_name == model_name
            )
            .values(
                requests=ModelUsage.requests + 1,
                tokens=ModelUsage.tokens + request_tokens + completion_tokens
            )
        )
        return result.rowcount > 0
```

### 依赖注入方式
```python
# 在路由中使用
from fastapi import Depends
from app.database.repositories.api_key_repository import ApiKeyRepository

async def get_api_key_repo(session: AsyncSession = Depends(get_db_session)) -> ApiKeyRepository:
    return ApiKeyRepository(session, ApiKey)

@router.post("/check-usage")
async def check_usage(
    request: Request,
    repo: ApiKeyRepository = Depends(get_api_key_repo)
):
    data = await request.json()
    existing_key = await repo.get_by_phone(data.get("phone"))
    ...
```

---

## 3. API速率限制

### 依赖安装
```
slowapi==0.1.9
```

### 目录结构
```
app/middleware/
├── __init__.py
├── auth.py              # 保持不变
├── logging.py           # 保持不变
└── rate_limit.py        # 新增
```

### `rate_limit.py`
```python
from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request

def get_identifier(request: Request) -> str:
    """优先使用API Key作为限流标识，否则使用IP"""
    auth_header = request.headers.get("Authorization", "")
    _, _, api_key = auth_header.partition(" ")
    return api_key if api_key else get_remote_address(request)

limiter = Limiter(
    key_func=get_identifier,
    default_limits=["60/minute"],
    storage_uri="memory://",
)

def rate_limit_exceeded_handler(request: Request, exc):
    """自定义超限响应"""
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "message": "Rate limit exceeded. Please try again later.",
                "type": "rate_limit_error",
                "code": "rate_limit_exceeded",
            }
        },
    )
```

### 配置扩展
```python
# app/config/settings.py 新增
class RateLimitSettings(BaseSettings):
    API_KEY_RATE_LIMIT: str = "60/minute"
    IP_RATE_LIMIT: str = "100/minute"
    REGISTER_RATE_LIMIT: str = "5/minute"
    RATE_LIMIT_STORAGE: str = "memory"
    REDIS_URL: str | None = None
```

### 应用中间件
```python
# app/main.py
from app.middleware.rate_limit import limiter, rate_limit_exceeded_handler

app = create_application()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
```

### 使用示例
```python
# app/api/user.py
from app.middleware.rate_limit import limiter

@router.post("/generate-api-key")
@limiter.limit("5/minute")
async def generate_api_key(request: Request, ...):
    ...

# app/api/llm.py
@router.post("/v1/chat/completions")
@limiter.limit("60/minute")
async def proxy_handler_chat(request: Request, ...):
    ...
```

---

## 验收标准

### 路由拆分
- [ ] `app/api/` 下有 `__init__.py`, `user.py`, `admin.py`, `llm.py`, `server.py`
- [ ] 各文件行数 < 500
- [ ] 所有API端点功能正常

### 数据库统一 ✅ (已完成 2026-01-22)
- [x] 新增 `base_repository.py` 和 `repositories/` 目录
- [x] 路由中无原生 `text()` SQL调用
- [x] 并发更新使用原子操作（`+=` 方式）
- [x] `routes.py` 使用 Repository 替代原生SQL
- [x] `api_service.py` 使用 Repository
- [x] `usage_queue.py` 使用 Repository
- [x] `llm_service.py` 使用 Repository

### 速率限制
- [ ] 注册接口限制 5次/分钟
- [ ] LLM接口限制 60次/分钟
- [ ] 超限返回 429 状态码和标准错误格式
