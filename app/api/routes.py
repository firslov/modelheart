import asyncio
import json
import os
import re
import time
from typing import Dict, Tuple
import httpx

from fastapi import APIRouter, HTTPException, Request, Response, Depends
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path

from app.config.settings import settings
from app.middleware.auth import admin_required, verify_admin, user_required, verify_user
from app.models.api_models import ApiKeyUsage
from app.models.queue_models import UsageEventData, UsageEventType
from app.services.api_service import ApiService
from app.services.llm_service import LLMService
from app.utils.helpers import get_current_time, log_api_usage
from app.utils.logging_config import get_logger
from app.database.database import get_db_session
from app.database.repositories import (
    get_api_key_repo,
    ApiKeyRepository,
)
import bcrypt

logger = get_logger(__name__)

router = APIRouter()


async def _handle_llm_server_action(request, api_service, data, session: AsyncSession):
    """处理LLM服务器操作的核心逻辑"""
    action = data.get("action")
    url = data.get("url")
    config = data.get("config", {})
    model_status = data.get("status")

    # 解码URL
    from urllib.parse import unquote

    url = unquote(url)

    # 处理不同操作
    if action == "add":
        # 添加新服务器 - 直接使用update_llm_server方法
        # 如果服务器已存在，update_llm_server会更新它；如果不存在，会创建新的
        await api_service.update_llm_server(url, config, session)
    elif action == "update":
        old_url = data.get("oldUrl")

        if old_url and old_url != url:
            # 如果URL改变了，先删除旧的服务器，再添加新的
            # 检查新URL是否已存在
            servers_data = await api_service.load_llm_servers(session)
            if old_url in servers_data:
                # 删除旧服务器
                del servers_data[old_url]
            # 添加/更新新服务器
            servers_data[url] = config
            # 使用save_llm_servers保存所有服务器
            await api_service.save_llm_servers(servers_data, session)
        else:
            # 只更新当前服务器的配置
            await api_service.update_llm_server(url, config, session)
    elif action == "delete":
        # 删除服务器 - 加载现有服务器，删除指定服务器
        servers_data = await api_service.load_llm_servers(session)
        if url in servers_data:
            del servers_data[url]
            await api_service.save_llm_servers(servers_data, session)
    elif action == "toggle_status" and model_status is not None:
        # 切换模型状态 - 只更新特定模型的status
        model_id = data.get("model")
        if model_id:
            # 加载当前服务器配置
            servers_data = await api_service.load_llm_servers(session)
            if url in servers_data and model_id in servers_data[url].get("model", {}):
                # 只更新该模型的status，其他配置保持不变
                server_config = servers_data[url].copy()
                if "model" in server_config and model_id in server_config["model"]:
                    server_config["model"][model_id]["status"] = model_status
                    # 使用update_llm_server方法只更新这个服务器
                    await api_service.update_llm_server(url, server_config, session)
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

    # 重新初始化LLM资源
    llm_service = request.app.state.app.llm_service
    await llm_service.init_llm_resources_from_db(session)

    return {"status": "success"}


@router.get("/get-llm-servers")
@admin_required
async def get_llm_servers(
    request: Request, session: AsyncSession = Depends(get_db_session)
):
    """获取LLM服务器列表(需要管理员权限)"""
    try:
        _, api_service = get_services(request)
        servers_data = await api_service.load_llm_servers(session)
        return servers_data
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error(f"Error loading LLM servers: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Error loading LLM servers: {str(e)}"
        )


@router.get("/circuit-breaker-stats")
@admin_required
async def get_circuit_breaker_stats(request: Request):
    """获取熔断器状态（需要管理员权限）

    返回所有服务器的熔断器状态，包括：
    - 当前状态 (closed/open/half_open)
    - 失败次数
    - 最后失败时间
    - 总请求数和失败数
    """
    try:
        llm_service, _ = get_services(request)
        return llm_service.get_circuit_breaker_stats()
    except Exception as e:
        import logging
        logging.error(f"Error getting circuit breaker stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error getting circuit breaker stats: {str(e)}"
        )


@router.post("/reset-circuit-breaker")
@admin_required
async def reset_circuit_breaker(request: Request):
    """重置熔断器状态（需要管理员权限）

    用于手动恢复被熔断的服务器。

    请求体：
    {
        "server_key": "api.example.com"  // 可选，不传则重置所有
    }
    """
    try:
        llm_service, _ = get_services(request)
        data = await request.json() if request.headers.get("content-type") == "application/json" else {}
        server_key = data.get("server_key")

        await llm_service.reset_circuit_breaker(server_key)

        return {
            "status": "success",
            "message": f"Circuit breaker reset for {'all servers' if not server_key else server_key}"
        }
    except Exception as e:
        import logging
        logging.error(f"Error resetting circuit breaker: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error resetting circuit breaker: {str(e)}"
        )


@router.post("/update-llm-servers")
@admin_required
async def update_llm_servers(
    request: Request, session: AsyncSession = Depends(get_db_session)
):
    """更新LLM服务器列表"""
    try:
        _, api_service = get_services(request)
        data = await request.json()
        return await _handle_llm_server_action(request, api_service, data, session)
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error(f"Error updating LLM servers: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error updating LLM servers: {str(e)}",
            headers={"X-Error-Details": str(e)},
        )


@router.get("/models")
@router.get("/v1/models")
async def list_models(
    request: Request, session: AsyncSession = Depends(get_db_session)
):
    """Get available models list - 使用数据库数据优化性能"""
    try:
        _, api_service = get_services(request)
        config = await api_service.load_llm_servers(session)

        models = []
        for server_url, server_info in config.items():
            device = server_info.get("device", "unknown")
            for model_id, model_info in server_info.get("model", {}).items():
                if model_info.get("status", False):
                    models.append(
                        {
                            "id": model_id,
                            "object": "model",
                            "owned_by": device,
                            "key": model_id,
                        }
                    )

        return {"object": "list", "data": models}
    except Exception as e:
        import logging
        logging.error(f"Error loading models: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error loading models: {str(e)}")


templates = Jinja2Templates(directory=settings.TEMPLATES_DIR)


def get_services(request: Request) -> tuple[LLMService, ApiService]:
    """获取服务实例"""
    app = request.app.state.app
    return app.llm_service, app.api_service


def get_usage_queue(request: Request):
    """获取用量队列实例"""
    return request.app.state.app.usage_queue


@router.get("/get-models")
async def get_models(request: Request, session: AsyncSession = Depends(get_db_session)):
    """获取可用的模型列表 - 使用数据库数据优化性能"""
    try:
        _, api_service = get_services(request)
        config = await api_service.load_llm_servers(session)

        # 获取所有活跃模型
        models = []
        for server_url, server_info in config.items():
            for model_id, model_info in server_info.get("model", {}).items():
                if model_info.get("status", False):
                    models.append(model_id)

        return {"models": models}

    except Exception as e:
        import logging
        logging.error(f"Error loading models: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error loading models: {str(e)}")


@router.get("/")
async def home():
    """首页"""
    return FileResponse(os.path.join(settings.STATIC_DIR, "index.html"))


@router.get("/login")
async def login_page(request: Request):
    """登录页面"""
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
async def login(request: Request):
    """处理登录请求"""
    # 支持两种格式：JSON 和表单数据
    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        data = await request.json()
        username = data.get("username")
        password = data.get("password")
        accept = request.headers.get("accept", "")
    else:
        # 表单数据格式
        form_data = await request.form()
        username = form_data.get("username")
        password = form_data.get("password")
        accept = ""  # 表单提交不使用JSON响应

    if verify_admin(username, password):
        request.session["authenticated"] = True
        request.session["is_admin"] = True
        if "application/json" in accept:
            return {"status": "success"}
        return RedirectResponse(url="/dashboard", status_code=303)

    # 登录失败
    if "application/json" in accept:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    else:
        # 表单提交失败，返回登录页面并显示错误
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "用户名或密码错误"
            }
        )


@router.get("/logout")
async def logout(request: Request):
    """退出登录"""
    request.session.clear()
    return RedirectResponse(url="/")


# ========================================
# 用户认证路由
# ========================================


@router.post("/user/register")
async def user_register(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    api_key_repo: ApiKeyRepository = Depends(get_api_key_repo),
):
    """用户注册"""
    try:
        data = await request.json()
        phone = data.get("phone", "")
        password = data.get("password", "")

        if not phone or not password:
            raise HTTPException(status_code=400, detail="手机号和密码不能为空")

        if not re.match(r"^1[3-9]\d{9}$", phone):
            raise HTTPException(status_code=400, detail="请输入有效的手机号")

        if len(password) < 6:
            raise HTTPException(status_code=400, detail="密码长度至少6位")
        if len(password) > 72:
            raise HTTPException(status_code=400, detail="密码长度不能超过72个字符")

        _, api_service = get_services(request)

        # 检查是否已存在该手机号
        existing_key = await api_key_repo.get_by_phone(phone)

        if existing_key:
            raise HTTPException(status_code=400, detail="该手机号已注册")

        # 生成新的API密钥
        new_key = await api_service.generate_api_key(session)

        # 更新记录，添加手机号和密码
        api_key_record = await api_key_repo.get_by_api_key(new_key)
        if api_key_record:
            api_key_record.phone = phone
            api_key_record.password_hash = bcrypt.hashpw(
                password.encode(), bcrypt.gensalt()
            ).decode()
            await session.commit()

        # 设置session
        request.session["user_authenticated"] = True
        request.session["user_phone"] = phone
        request.session["user_api_key"] = new_key

        return {"status": "success", "api_key": new_key}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"User registration failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"注册失败: {str(e)}")


@router.post("/user/login")
async def user_login(
    request: Request,
    api_key_repo: ApiKeyRepository = Depends(get_api_key_repo),
):
    """用户登录"""
    try:
        data = await request.json()
        phone = data.get("phone", "")
        password = data.get("password", "")

        if not phone or not password:
            raise HTTPException(status_code=400, detail="手机号和密码不能为空")

        if not re.match(r"^1[3-9]\d{9}$", phone):
            raise HTTPException(status_code=400, detail="请输入有效的手机号")

        # 检查用户是否存在
        api_key_record = await api_key_repo.get_by_phone(phone)

        if not api_key_record:
            raise HTTPException(status_code=404, detail="用户不存在")

        # 验证密码
        if not api_key_record.password_hash:
            raise HTTPException(status_code=401, detail="账户异常，请联系管理员")

        if not verify_user(password, api_key_record.password_hash):
            raise HTTPException(status_code=401, detail="密码错误")

        # 设置session
        request.session["user_authenticated"] = True
        request.session["user_phone"] = phone
        request.session["user_api_key"] = api_key_record.api_key

        return {"status": "success", "redirect": "/user"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"User login failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"登录失败: {str(e)}")


@router.get("/user/logout")
async def user_logout(request: Request):
    """用户退出登录"""
    # 只清除用户相关的session
    request.session.pop("user_authenticated", None)
    request.session.pop("user_phone", None)
    request.session.pop("user_api_key", None)
    return RedirectResponse(url="/", status_code=303)


@router.get("/user/info")
async def get_user_info(
    request: Request,
    api_key_repo: ApiKeyRepository = Depends(get_api_key_repo),
):
    """获取用户信息"""
    if not request.session.get("user_authenticated"):
        raise HTTPException(status_code=401, detail="请先登录")

    phone = request.session.get("user_phone")
    if not phone:
        raise HTTPException(status_code=401, detail="会话已过期，请重新登录")

    api_key_record = await api_key_repo.get_by_phone_with_usages(phone)
    if not api_key_record:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 获取模型使用统计
    model_usage = {}
    for mu in api_key_record.model_usages:
        model_usage[mu.model_name] = {
            "requests": mu.requests,
            "tokens": mu.tokens
        }

    return {
        "phone": api_key_record.phone,
        "api_key": api_key_record.api_key,
        "usage": api_key_record.usage or 0,
        "limit": api_key_record.limit_value or 1000000,
        "remaining": max(0, (api_key_record.limit_value or 1000000) - (api_key_record.usage or 0)),
        "reqs": api_key_record.reqs or 0,
        "created_at": api_key_record.created_at_str or (api_key_record.created_at.strftime("%Y-%m-%d %H:%M:%S") if api_key_record.created_at else None),
        "model_usage": model_usage,
    }


@router.get("/user", response_class=HTMLResponse)
@user_required
async def user_page(
    request: Request,
    api_key_repo: ApiKeyRepository = Depends(get_api_key_repo),
):
    """用户页面"""
    phone = request.session.get("user_phone")
    if not phone:
        return RedirectResponse(url="/", status_code=303)

    api_key_record = await api_key_repo.get_by_phone_with_usages(phone)
    if not api_key_record:
        request.session.clear()
        return RedirectResponse(url="/", status_code=303)

    # 获取模型使用统计
    model_usage = []
    for mu in api_key_record.model_usages:
        model_usage.append({
            "name": mu.model_name,
            "requests": mu.requests,
            "tokens": mu.tokens
        })

    return templates.TemplateResponse(
        "user.html",
        {
            "request": request,
            "phone": api_key_record.phone,
            "api_key": api_key_record.api_key,
            "usage": api_key_record.usage or 0,
            "limit": api_key_record.limit_value or 1000000,
            "remaining": max(0, (api_key_record.limit_value or 1000000) - (api_key_record.usage or 0)),
            "reqs": api_key_record.reqs or 0,
            "created_at": api_key_record.created_at_str or (api_key_record.created_at.strftime("%Y-%m-%d %H:%M:%S") if api_key_record.created_at else "未知"),
            "model_usage": model_usage,
            "current_time": get_current_time(),
        },
    )


@router.post("/generate-api-key")
async def generate_api_key(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    api_key_repo: ApiKeyRepository = Depends(get_api_key_repo),
):
    """生成新的API密钥 - 支持手机号和密码验证"""
    try:
        data = await request.json()
        phone = data.get("phone", "")
        password = data.get("password", "")

        if not phone or not password:
            raise HTTPException(status_code=400, detail="手机号和密码不能为空")

        if not re.match(r"^1[3-9]\d{9}$", phone):
            raise HTTPException(status_code=400, detail="请输入有效的手机号")

        if len(password) < 6:
            raise HTTPException(status_code=400, detail="密码长度至少6位")
        if len(password) > 72:
            raise HTTPException(status_code=400, detail="密码长度不能超过72个字符")

        _, api_service = get_services(request)

        # 检查是否已存在该手机号
        existing_key = await api_key_repo.get_by_phone(phone)

        if existing_key:
            # 如果手机号已存在，提示用户已注册
            return JSONResponse(status_code=400, content={"detail": "用户已注册"})
        else:
            # 生成新的API密钥
            new_key = await api_service.generate_api_key(session)

            # 更新记录，添加手机号和密码
            api_key_record = await api_key_repo.get_by_api_key(new_key)
            if api_key_record:
                api_key_record.phone = phone
                api_key_record.password_hash = bcrypt.hashpw(
                    password.encode(), bcrypt.gensalt()
                ).decode()
                await session.commit()

            return {"api_key": new_key}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成API密钥失败: {str(e)}")


@router.post("/check-usage")
async def check_usage(
    request: Request,
    api_key_repo: ApiKeyRepository = Depends(get_api_key_repo),
):
    """查询API密钥使用额度"""
    try:
        data = await request.json()
        phone = data.get("phone", "")
        password = data.get("password", "")

        if not phone or not password:
            raise HTTPException(status_code=400, detail="手机号和密码不能为空")

        if not re.match(r"^1[3-9]\d{9}$", phone):
            raise HTTPException(status_code=400, detail="请输入有效的手机号")

        # 检查是否已存在该手机号
        existing_key = await api_key_repo.get_by_phone(phone)

        if not existing_key:
            raise HTTPException(status_code=404, detail="未找到该手机号对应的账户")

        # 验证密码 - 使用bcrypt验证
        try:
            if not bcrypt.checkpw(
                password.encode(), existing_key.password_hash.encode()
            ):
                return JSONResponse(
                    status_code=401, content={"error": "密码错误", "detail": "密码错误"}
                )
        except Exception:
            return JSONResponse(
                status_code=401, content={"error": "密码错误", "detail": "密码错误"}
            )

        # 返回使用额度信息
        usage = existing_key.usage or 0
        limit = existing_key.limit_value or 1000000  # 默认限额1,000,000 tokens
        remaining = max(0, limit - usage)

        return {
            "api_key": existing_key.api_key,
            "usage": usage,
            "limit": limit,
            "remaining": remaining,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询额度失败: {str(e)}")


@router.post("/update-api-key-limit")
@admin_required
async def update_api_key_limit(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    api_key_repo: ApiKeyRepository = Depends(get_api_key_repo),
):
    """更新API密钥的使用限额"""
    data = await request.json()
    api_key = data.get("api_key")
    new_limit = data.get("new_limit")

    if not api_key or new_limit is None:
        raise HTTPException(
            status_code=400, detail="API key and new limit are required"
        )

    # 使用Repository更新限额
    success = await api_key_repo.update_limit(api_key, new_limit)
    if not success:
        raise HTTPException(status_code=404, detail="API key not found")

    # 提交事务
    await session.commit()

    return {"status": "success"}


@router.post("/reset-api-key-usage")
@admin_required
async def reset_api_key_usage(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    api_key_repo: ApiKeyRepository = Depends(get_api_key_repo),
):
    """重置API密钥使用量"""
    data = await request.json()
    api_key = data.get("api_key")
    if not api_key:
        raise HTTPException(status_code=400, detail="API key is required")

    # 使用Repository重置使用量
    success = await api_key_repo.reset_usage(api_key)
    if not success:
        raise HTTPException(status_code=404, detail="API key not found")

    # 提交事务
    await session.commit()

    return {"status": "success"}


@router.post("/revoke-api-key")
@admin_required
async def revoke_api_key(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    api_key_repo: ApiKeyRepository = Depends(get_api_key_repo),
):
    """撤销API密钥"""
    data = await request.json()
    api_key = data.get("api_key")
    if not api_key:
        raise HTTPException(status_code=400, detail="API key is required")

    # 使用Repository删除API密钥
    success = await api_key_repo.delete_by_api_key(api_key)
    if not success:
        raise HTTPException(status_code=404, detail="API key not found")

    # 提交事务
    await session.commit()

    return {"status": "success"}


@router.post("/change-user-password")
@admin_required
async def change_user_password(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    api_key_repo: ApiKeyRepository = Depends(get_api_key_repo),
):
    """管理员修改用户密码"""
    try:
        data = await request.json()
        api_key = data.get("api_key")
        new_password = data.get("new_password")

        if not api_key or not new_password:
            raise HTTPException(
                status_code=400, detail="API key and new password are required"
            )

        if len(new_password) < 6:
            raise HTTPException(status_code=400, detail="密码长度至少6位")
        if len(new_password) > 72:
            raise HTTPException(status_code=400, detail="密码长度不能超过72个字符")

        # 检查API密钥是否存在
        api_key_record = await api_key_repo.get_by_api_key(api_key)

        if not api_key_record:
            raise HTTPException(status_code=404, detail="未找到该API密钥对应的用户")

        # 更新密码哈希
        api_key_record.password_hash = bcrypt.hashpw(
            new_password.encode(), bcrypt.gensalt()
        ).decode()
        await session.commit()

        return {"status": "success", "message": "密码修改成功"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"修改密码失败: {str(e)}")


@router.get("/dashboard", response_class=HTMLResponse)
@admin_required
async def usage_dashboard(
    request: Request,
    api_key_repo: ApiKeyRepository = Depends(get_api_key_repo),
):
    """用量统计和管理仪表盘"""
    # 使用Repository获取数据，包括模型使用统计
    api_keys_data = await api_key_repo.get_all_with_usages()

    # 计算统计信息
    total_usage = sum(key.usage or 0 for key in api_keys_data)
    total_entries = len(api_keys_data)
    total_reqs = sum(key.reqs or 0 for key in api_keys_data)

    # 统计不同使用量区间的数量
    less_than_100 = sum(1 for key in api_keys_data if (key.usage or 0) < 100)
    between_100_and_10000 = sum(
        1 for key in api_keys_data if 100 <= (key.usage or 0) < 10000
    )
    more_than_10000 = sum(1 for key in api_keys_data if (key.usage or 0) >= 10000)

    # 构建API密钥列表
    api_keys = []
    for key in api_keys_data:
        # 使用to_dict方法获取完整数据，包括model_usage
        key_data = key.to_dict()
        key_data["key"] = key.api_key
        api_keys.append(key_data)

    return templates.TemplateResponse(
        "dashboard_manage.html",
        {
            "request": request,
            "total_usage": total_usage,
            "total_entries": total_entries,
            "total_reqs": total_reqs,
            "less_than_100": less_than_100,
            "between_100_and_10000": between_100_and_10000,
            "more_than_10000": more_than_10000,
            "api_keys": api_keys,
            "current_time": get_current_time(),
        },
    )


# ========================================
# 客户端下载
# ========================================

DOWNLOAD_DIR = Path(__file__).parent.parent.parent / "downloads"


@router.get("/downloads")
async def list_downloads():
    """获取可下载的客户端列表"""
    available_files = []

    # 检查 macOS 客户端
    mac_files = list(DOWNLOAD_DIR.glob("*.dmg")) + list(DOWNLOAD_DIR.glob("*.pkg"))
    for f in mac_files:
        available_files.append({
            "platform": "macOS",
            "filename": f.name,
            "url": f"/download/{f.name}",
            "size": f.stat().st_size if f.exists() else 0
        })

    # 检查 Windows 客户端
    win_files = list(DOWNLOAD_DIR.glob("*.exe")) + list(DOWNLOAD_DIR.glob("*.zip"))
    for f in win_files:
        available_files.append({
            "platform": "Windows",
            "filename": f.name,
            "url": f"/download/{f.name}",
            "size": f.stat().st_size if f.exists() else 0
        })

    return {"files": available_files}


@router.get("/download/{filename}")
async def download_client(filename: str):
    """安全下载客户端文件"""
    # 安全检查：确保文件名不包含路径遍历字符
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    file_path = DOWNLOAD_DIR / filename

    # 检查文件是否存在
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    # 检查文件扩展名是否允许
    allowed_extensions = {".dmg", ".pkg", ".exe", ".zip"}
    if file_path.suffix.lower() not in allowed_extensions:
        raise HTTPException(status_code=403, detail="File type not allowed")

    # 根据平台设置合适的 Content-Type
    content_type = "application/octet-stream"
    if filename.endswith(".dmg"):
        content_type = "application/x-apple-diskimage"
    elif filename.endswith(".pkg"):
        content_type = "application/vnd.apple.installer+xml"
    elif filename.endswith(".exe"):
        content_type = "application/vnd.microsoft.portable-executable"
    elif filename.endswith(".zip"):
        content_type = "application/zip"

    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        }
    )


@router.options("/v1/chat/completions")
@router.options("/chat/completions")
@router.options("/v1/completions")
@router.options("/completions")
async def options_handler():
    """处理 OPTIONS 请求"""
    return Response(status_code=200)


@router.post("/v1/chat/completions")
@router.post("/chat/completions")
async def proxy_handler_chat(
    request: Request, session: AsyncSession = Depends(get_db_session)
):
    """请求转发处理"""
    llm_service, api_service = get_services(request)
    usage_queue = get_usage_queue(request)

    # 身份验证
    auth_header = request.headers.get("Authorization", "")
    _, _, api_key = auth_header.partition(" ")
    await api_service.validate_api_key(api_key, session)
    await api_service.check_usage_limit(api_key, session)

    # 请求处理
    req_data = await request.json()
    model = req_data.get("model")

    # 获取目标服务器
    target_server = llm_service.get_target_server(model)
    target = f"{target_server}{request.url.path.replace('/v1', '', 1)}"

    # 构造请求头
    headers = llm_service.get_auth_header(model, api_key)

    try:
        # 流式响应处理
        if req_data.get("stream", False):
            # 在流式响应前获取模型权重，避免在流式结束后使用已关闭的 session
            input_weight, output_weight = await api_service._get_model_weights(model, session)

            async def stream_wrapper():
                start_time = time.time()
                chunk_count = 0
                max_retries = 1

                for attempt in range(max_retries + 1):
                    try:
                        client_stream = await llm_service.forward_request(
                            target, req_data, headers, stream=True
                        )

                        async with client_stream as response:
                            first_chunk_time = None
                            async for chunk in response.aiter_text():
                                if first_chunk_time is None:
                                    first_chunk_time = time.time()
                                    first_chunk_delay = first_chunk_time - start_time
                                    logger.debug(f"First chunk | model={model} | delay={first_chunk_delay:.3f}s")

                                chunk_count += 1
                                yield chunk

                        end_time = time.time()
                        total_duration = end_time - start_time

                        # 记录流式响应性能指标
                        logger.info(
                            f"Stream completed | model={model} | "
                            f"duration={total_duration:.3f}s | chunks={chunk_count} | "
                            f"first_chunk={first_chunk_delay if 'first_chunk_delay' in locals() else 'N/A':.3f}s"
                        )

                        # 流式响应结束后，将统计事件加入队列（非阻塞）
                        await usage_queue.enqueue(
                            UsageEventData(
                                event_type=UsageEventType.UPDATE_USAGE,
                                api_key=api_key,
                                model=model,
                                server_url=target_server,
                                prompt_tokens=0,
                                completion_tokens=0,
                                input_token_weight=input_weight,
                                output_token_weight=output_weight,
                                request_data=req_data,
                            )
                        )
                        await usage_queue.enqueue(
                            UsageEventData(
                                event_type=UsageEventType.INCREMENT_MODEL_REQS,
                                api_key=api_key,
                                model=model,
                                server_url=target_server,
                            )
                        )
                        break  # 成功完成，跳出重试循环

                    except httpx.RemoteProtocolError as exc:
                        logger.warning(
                            f"Stream connection error (attempt {attempt + 1}/{max_retries + 1}) model={model}: {exc}"
                        )
                        if attempt < max_retries:
                            await asyncio.sleep(0.5)
                            continue
                        else:
                            error_data = {
                                "error": {
                                    "message": f"上游服务连接中断: {str(exc)}",
                                    "type": "connection_error",
                                    "code": "connection_terminated"
                                }
                            }
                            yield f"data: {json.dumps(error_data)}\n\n"
                            yield "data: [DONE]\n\n"

                    except Exception as exc:
                        logger.error(f"Stream error model={model}: {exc}")
                        error_data = {
                            "error": {
                                "message": f"流式响应错误: {str(exc)}",
                                "type": "stream_error"
                            }
                        }
                        yield f"data: {json.dumps(error_data)}\n\n"
                        yield "data: [DONE]\n\n"

            return StreamingResponse(
                stream_wrapper(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",  # 禁用Nginx缓冲
                },
            )

        # 普通响应处理
        response_text = await llm_service.forward_request(target, req_data, headers)

        try:
            response = json.loads(response_text)

            # 获取模型权重
            input_weight, output_weight = await api_service._get_model_weights(model, session)

            # 将统计事件加入队列
            if "usage" in response:
                await usage_queue.enqueue(
                    UsageEventData(
                        event_type=UsageEventType.UPDATE_USAGE,
                        api_key=api_key,
                        model=model,
                        server_url=target_server,
                        prompt_tokens=response["usage"].get("prompt_tokens", 0),
                        completion_tokens=response["usage"].get("completion_tokens", 0),
                        input_token_weight=input_weight,
                        output_token_weight=output_weight,
                    )
                )

            # 入队模型请求计数事件
            await usage_queue.enqueue(
                UsageEventData(
                    event_type=UsageEventType.INCREMENT_MODEL_REQS,
                    api_key=api_key,
                    model=model,
                    server_url=target_server,
                )
            )

            return JSONResponse(response)
        except json.JSONDecodeError as e:
            return JSONResponse(
                {"error": "Invalid response from upstream server", "message": str(e)},
                status_code=500,
            )

    except HTTPException as e:
        return JSONResponse({"error": str(e.detail)}, status_code=e.status_code)
    except Exception as e:
        logger.error(f"chat/completions error: {e}", exc_info=True)
        return JSONResponse({"error": "Internal server error"}, status_code=500)


@router.post("/v1/embeddings")
@router.post("/embeddings")
async def proxy_handler_embeddings(
    request: Request, session: AsyncSession = Depends(get_db_session)
):
    """处理embeddings请求转发"""
    llm_service, api_service = get_services(request)
    usage_queue = get_usage_queue(request)

    # 身份验证
    auth_header = request.headers.get("Authorization", "")
    _, _, api_key = auth_header.partition(" ")
    await api_service.validate_api_key(api_key, session)
    await api_service.check_usage_limit(api_key, session)

    # 请求处理
    req_data = await request.json()
    model = req_data.get("model")

    # 获取目标服务器
    target_server = llm_service.get_target_server(model)
    target = f"{target_server}{request.url.path.replace('/v1', '', 1)}"

    # 构造请求头
    headers = llm_service.get_auth_header(model, api_key)

    try:
        # 转发请求
        response_text = await llm_service.forward_request(target, req_data, headers)
        response = json.loads(response_text)

        # 获取模型权重
        input_weight, output_weight = await api_service._get_model_weights(model, session)

        # 更新用量 - embeddings 接口只有 prompt_tokens
        if "usage" in response and "prompt_tokens" in response["usage"]:
            await usage_queue.enqueue(
                UsageEventData(
                    event_type=UsageEventType.UPDATE_USAGE,
                    api_key=api_key,
                    model=model,
                    server_url=target_server,
                    prompt_tokens=response["usage"]["prompt_tokens"],
                    completion_tokens=0,  # embeddings 没有 completion_tokens
                    input_token_weight=input_weight,
                    output_token_weight=output_weight,
                )
            )

        # 入队模型请求计数事件
        await usage_queue.enqueue(
            UsageEventData(
                event_type=UsageEventType.INCREMENT_MODEL_REQS,
                api_key=api_key,
                model=model,
                server_url=target_server,
            )
        )

        return JSONResponse(response)

    except json.JSONDecodeError as e:
        return JSONResponse(
            {"error": "Invalid response from upstream server", "message": str(e)},
            status_code=500,
        )
    except HTTPException as e:
        return JSONResponse({"error": str(e.detail)}, status_code=e.status_code)
    except Exception as e:
        logger.error(f"embeddings error: {e}", exc_info=True)
        return JSONResponse({"error": "Internal server error"}, status_code=500)


@router.post("/v1/completions")
@router.post("/completions")
async def proxy_handler_completions(
    request: Request, session: AsyncSession = Depends(get_db_session)
):
    """请求转发处理"""
    llm_service, api_service = get_services(request)
    usage_queue = get_usage_queue(request)

    # 身份验证
    auth_header = request.headers.get("Authorization", "")
    _, _, api_key = auth_header.partition(" ")
    await api_service.validate_api_key(api_key, session)

    # 请求处理
    req_data = await request.json()
    model = req_data.get("model")

    # 获取目标服务器
    target_server = llm_service.get_target_server(model)
    target = f"{target_server}{request.url.path.replace('/v1', '', 1)}"

    # 构造请求头
    headers = llm_service.get_auth_header(model, api_key)

    try:
        # 流式响应处理
        if req_data.get("stream", False):
            async def stream_wrapper():
                max_retries = 1

                for attempt in range(max_retries + 1):
                    try:
                        client_stream = await llm_service.forward_request(
                            target, req_data, headers, stream=True
                        )

                        async with client_stream as response:
                            async for chunk in response.aiter_text():
                                yield chunk

                        # 流式响应结束后，将统计事件加入队列
                        await usage_queue.enqueue(
                            UsageEventData(
                                event_type=UsageEventType.UPDATE_USAGE,
                                api_key=api_key,
                                model=model,
                                server_url=target_server,
                                request_data=req_data,
                            )
                        )
                        await usage_queue.enqueue(
                            UsageEventData(
                                event_type=UsageEventType.INCREMENT_MODEL_REQS,
                                api_key=api_key,
                                model=model,
                                server_url=target_server,
                            )
                        )
                        break  # 成功完成

                    except httpx.RemoteProtocolError as exc:
                        logger.warning(
                            f"Stream connection error (attempt {attempt + 1}/{max_retries + 1}) model={model}: {exc}"
                        )
                        if attempt < max_retries:
                            await asyncio.sleep(0.5)
                            continue
                        else:
                            error_data = {
                                "error": {
                                    "message": f"上游服务连接中断: {str(exc)}",
                                    "type": "connection_error",
                                    "code": "connection_terminated"
                                }
                            }
                            yield f"data: {json.dumps(error_data)}\n\n"
                            yield "data: [DONE]\n\n"

                    except Exception as exc:
                        logger.error(f"Stream error model={model}: {exc}")
                        error_data = {
                            "error": {
                                "message": f"流式响应错误: {str(exc)}",
                                "type": "stream_error"
                            }
                        }
                        yield f"data: {json.dumps(error_data)}\n\n"
                        yield "data: [DONE]\n\n"

            return StreamingResponse(
                stream_wrapper(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",  # 禁用Nginx缓冲
                },
            )

        # 普通响应处理
        response_text = await llm_service.forward_request(target, req_data, headers)

        try:
            response = json.loads(response_text)

            # 获取模型权重
            input_weight, output_weight = await api_service._get_model_weights(model, session)

            # 将统计事件加入队列
            if "usage" in response:
                await usage_queue.enqueue(
                    UsageEventData(
                        event_type=UsageEventType.UPDATE_USAGE,
                        api_key=api_key,
                        model=model,
                        server_url=target_server,
                        prompt_tokens=response["usage"].get("prompt_tokens", 0),
                        completion_tokens=response["usage"].get("completion_tokens", 0),
                        input_token_weight=input_weight,
                        output_token_weight=output_weight,
                    )
                )

            # 入队模型请求计数事件
            await usage_queue.enqueue(
                UsageEventData(
                    event_type=UsageEventType.INCREMENT_MODEL_REQS,
                    api_key=api_key,
                    model=model,
                    server_url=target_server,
                )
            )

            return JSONResponse(response)
        except json.JSONDecodeError as e:
            return JSONResponse(
                {"error": "Invalid response from upstream server", "message": str(e)},
                status_code=500,
            )

    except HTTPException as e:
        return JSONResponse({"error": str(e.detail)}, status_code=e.status_code)
    except Exception as e:
        logger.error(f"completions error: {e}", exc_info=True)
        return JSONResponse({"error": "Internal server error"}, status_code=500)


@router.options("/anthropic")
@router.options("/anthropic/v1/messages")
async def anthropic_options_handler():
    """处理 /anthropic OPTIONS 请求"""
    return Response(status_code=200)


@router.post("/anthropic")
@router.post("/anthropic/v1/messages")
async def anthropic_proxy_handler(
    request: Request, session: AsyncSession = Depends(get_db_session)
):
    """Anthropic API转发处理 - 不记录token使用，但统计请求数量"""
    llm_service, api_service = get_services(request)
    usage_queue = get_usage_queue(request)

    # 身份验证 - 验证API密钥存在
    auth_header = request.headers.get("Authorization", "")
    _, _, api_key = auth_header.partition(" ")

    if not api_key:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    # 验证API密钥有效性
    await api_service.validate_api_key(api_key, session)

    # 请求处理
    req_data = await request.json()
    model = req_data.get("model")

    # 获取目标服务器
    target_server = llm_service.get_target_server(model)

    # 记录请求日志
    masked_key = f"{api_key[:8]}...{api_key[-4:]}"
    logger.info(f"anthropic request | model={model} | key={masked_key} | server={target_server}")

    # 构建目标URL - 去掉用户路径中的/anthropic前缀
    original_path = request.url.path
    if original_path.startswith("/anthropic/v1/messages"):
        target = f"{target_server}/v1/messages"
    else:
        target = f"{target_server}"

    # 构造请求头 - 使用Anthropic格式的认证头
    headers = {
        "Authorization": f"Bearer {llm_service.app_state.cloud_models.get(model, api_key)}",
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",  # 添加Anthropic版本头
    }

    try:
        # 流式响应处理
        if req_data.get("stream", False):
            async def stream_wrapper():
                max_retries = 1

                for attempt in range(max_retries + 1):
                    try:
                        client_stream = await llm_service.forward_request(
                            target, req_data, headers, stream=True
                        )

                        async with client_stream as response:
                            async for chunk in response.aiter_text():
                                yield chunk

                        # 流式响应成功完成
                        logger.info(f"anthropic stream completed | model={model} | key={masked_key}")
                        # 将统计事件加入队列
                        await usage_queue.enqueue(
                            UsageEventData(
                                event_type=UsageEventType.UPDATE_ANTHROPIC_USAGE,
                                api_key=api_key,
                                model=model,
                            )
                        )
                        await usage_queue.enqueue(
                            UsageEventData(
                                event_type=UsageEventType.INCREMENT_MODEL_REQS,
                                api_key=api_key,
                                model=model,
                                server_url=target_server,
                            )
                        )
                        break  # 成功完成

                    except httpx.RemoteProtocolError as exc:
                        logger.warning(
                            f"Stream connection error (attempt {attempt + 1}/{max_retries + 1}) model={model}: {exc}"
                        )
                        if attempt < max_retries:
                            await asyncio.sleep(0.5)
                            continue
                        else:
                            # Anthropic 错误事件格式
                            yield f'event: error\n'
                            yield f'data: {json.dumps({"error": {"message": f"上游服务连接中断: {str(exc)}", "type": "connection_error"}})}\n\n'
                            yield 'event: message_stop\n'
                            yield 'data: {"type": "message_stop"}\n\n'

                    except Exception as exc:
                        logger.error(f"Stream error model={model}: {exc}")
                        yield f'event: error\n'
                        yield f'data: {json.dumps({"error": {"message": f"流式响应错误: {str(exc)}", "type": "stream_error"}})}\n\n'
                        yield 'event: message_stop\n'
                        yield 'data: {"type": "message_stop"}\n\n'

            return StreamingResponse(
                stream_wrapper(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",  # 禁用Nginx缓冲
                },
            )

        # 普通响应处理
        response_text = await llm_service.forward_request(target, req_data, headers)

        try:
            response = json.loads(response_text)

            # 普通响应成功
            logger.info(f"anthropic response completed | model={model} | key={masked_key}")

            # 将统计事件加入队列 - Anthropic 只记录请求次数
            await usage_queue.enqueue(
                UsageEventData(
                    event_type=UsageEventType.UPDATE_ANTHROPIC_USAGE,
                    api_key=api_key,
                    model=model,
                )
            )
            await usage_queue.enqueue(
                UsageEventData(
                    event_type=UsageEventType.INCREMENT_MODEL_REQS,
                    api_key=api_key,
                    model=model,
                    server_url=target_server,
                )
            )

            return JSONResponse(response)
        except json.JSONDecodeError as e:
            return JSONResponse(
                {"error": "Invalid response from upstream server", "message": str(e)},
                status_code=500,
            )

    except HTTPException as e:
        return JSONResponse({"error": str(e.detail)}, status_code=e.status_code)
    except Exception as e:
        logger.error(f"anthropic error: {e}", exc_info=True)
        return JSONResponse({"error": "Internal server error"}, status_code=500)
