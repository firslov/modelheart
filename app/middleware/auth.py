from functools import wraps
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
import bcrypt


def user_required(func):
    """用户登录验证装饰器"""

    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        if not request.session.get("user_authenticated"):
            accept = request.headers.get("accept", "")
            if "application/json" in accept:
                raise HTTPException(status_code=401, detail="User authentication required")
            return RedirectResponse(url="/", status_code=303)
        return await func(request, *args, **kwargs)

    return wrapper


def verify_user(password: str, password_hash: str) -> bool:
    """验证用户密码"""
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except Exception:
        return False


def login_required(func):
    """登录验证装饰器"""

    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        if not request.session.get("authenticated"):
            accept = request.headers.get("accept", "")
            if "application/json" in accept:
                raise HTTPException(status_code=401, detail="Authentication required")
            return RedirectResponse(url="/login", status_code=303)
        return await func(request, *args, **kwargs)

    return wrapper


def admin_required(func):
    """管理员验证装饰器"""

    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        if not request.session.get("is_admin"):
            accept = request.headers.get("accept", "")
            if "application/json" in accept:
                raise HTTPException(status_code=403, detail="Admin privileges required")
            return RedirectResponse(url="/login", status_code=303)
        return await func(request, *args, **kwargs)

    return wrapper


# 管理员凭据
ADMIN_CREDENTIALS = {"admin": "admin123"}  # 实际应用中应使用更安全的密码存储方式


def verify_admin(username: str, password: str) -> bool:
    """验证管理员凭据"""
    return ADMIN_CREDENTIALS.get(username) == password
