import json
import os
import re
from typing import Dict, Tuple

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

from app.config.settings import settings
from app.middleware.auth import admin_required, verify_admin
from app.models.api_models import ApiKeyUsage
from app.services.api_service import ApiService
from app.services.llm_service import LLMService
from app.utils.helpers import get_current_time, log_api_usage
from app.database.database import get_db_session
import bcrypt

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
        # 添加新服务器 - 加载现有服务器，然后添加新服务器
        servers_data = await api_service.load_llm_servers(session)
        servers_data[url] = config
        await api_service.save_llm_servers(servers_data, session)
    elif action == "update":
        old_url = data.get("oldUrl")

        if old_url and old_url != url:
            # 如果URL改变了，先删除旧的服务器，再添加新的
            servers_data = await api_service.load_llm_servers(session)
            if old_url in servers_data:
                del servers_data[old_url]
            servers_data[url] = config
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
            servers_data = await api_service.load_llm_servers(session)
            if url in servers_data and model_id in servers_data[url].get("model", {}):
                servers_data[url]["model"][model_id]["status"] = model_status
                await api_service.save_llm_servers(servers_data, session)
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
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error loading LLM servers: {str(e)}"
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
        raise HTTPException(status_code=500, detail=f"Error loading models: {str(e)}")


templates = Jinja2Templates(directory=settings.TEMPLATES_DIR)


def get_services(request: Request) -> tuple[LLMService, ApiService]:
    """获取服务实例"""
    app = request.app.state.app
    return app.llm_service, app.api_service


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
    data = await request.json()
    username = data.get("username")
    password = data.get("password")

    if verify_admin(username, password):
        request.session["authenticated"] = True
        request.session["is_admin"] = True
        accept = request.headers.get("accept", "")
        if "application/json" in accept:
            return {"status": "success"}
        return RedirectResponse(url="/get-usage", status_code=303)

    raise HTTPException(status_code=401, detail="Invalid credentials")


@router.get("/logout")
async def logout(request: Request):
    """退出登录"""
    request.session.clear()
    return RedirectResponse(url="/")


@router.post("/generate-api-key")
async def generate_api_key(
    request: Request, session: AsyncSession = Depends(get_db_session)
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
        from app.database.models import ApiKey
        from sqlalchemy import select

        result = await session.execute(select(ApiKey).where(ApiKey.phone == phone))
        existing_key = result.scalar_one_or_none()

        if existing_key:
            # 如果手机号已存在，提示用户已注册
            return JSONResponse(status_code=400, content={"detail": "用户已注册"})
        else:
            # 生成新的API密钥
            new_key = await api_service.generate_api_key(session)

            # 更新记录，添加手机号和密码
            result = await session.execute(
                select(ApiKey).where(ApiKey.api_key == new_key)
            )
            api_key_record = result.scalar_one_or_none()
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
    request: Request, session: AsyncSession = Depends(get_db_session)
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
        from app.database.models import ApiKey
        from sqlalchemy import select

        result = await session.execute(select(ApiKey).where(ApiKey.phone == phone))
        existing_key = result.scalar_one_or_none()

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
    request: Request, session: AsyncSession = Depends(get_db_session)
):
    """更新API密钥的使用限额"""
    data = await request.json()
    api_key = data.get("api_key")
    new_limit = data.get("new_limit")

    if not api_key or new_limit is None:
        raise HTTPException(
            status_code=400, detail="API key and new limit are required"
        )

    _, api_service = get_services(request)

    # 更新数据库中的限额
    from sqlalchemy import text

    await session.execute(
        text("UPDATE api_keys SET limit_value = :limit WHERE api_key = :api_key"),
        {"limit": new_limit, "api_key": api_key},
    )
    await session.commit()

    return {"status": "success"}


@router.post("/reset-api-key-usage")
@admin_required
async def reset_api_key_usage(
    request: Request, session: AsyncSession = Depends(get_db_session)
):
    """重置API密钥使用量"""
    data = await request.json()
    api_key = data.get("api_key")
    if not api_key:
        raise HTTPException(status_code=400, detail="API key is required")

    _, api_service = get_services(request)

    # 重置数据库中的使用量
    from sqlalchemy import text

    await session.execute(
        text("UPDATE api_keys SET usage = 0, reqs = 0 WHERE api_key = :api_key"),
        {"api_key": api_key},
    )
    await session.commit()

    return {"status": "success"}


@router.post("/revoke-api-key")
@admin_required
async def revoke_api_key(
    request: Request, session: AsyncSession = Depends(get_db_session)
):
    """撤销API密钥"""
    data = await request.json()
    api_key = data.get("api_key")
    if not api_key:
        raise HTTPException(status_code=400, detail="API key is required")

    _, api_service = get_services(request)

    # 从数据库中删除API密钥
    from sqlalchemy import text

    await session.execute(
        text("DELETE FROM api_keys WHERE api_key = :api_key"), {"api_key": api_key}
    )
    await session.commit()

    return {"status": "success"}


@router.post("/change-user-password")
@admin_required
async def change_user_password(
    request: Request, session: AsyncSession = Depends(get_db_session)
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
        from app.database.models import ApiKey
        from sqlalchemy import select

        result = await session.execute(select(ApiKey).where(ApiKey.api_key == api_key))
        api_key_record = result.scalar_one_or_none()

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


@router.get("/get-usage", response_class=HTMLResponse)
@admin_required
async def usage_dashboard(
    request: Request, session: AsyncSession = Depends(get_db_session)
):
    """用量统计和管理仪表盘"""
    _, api_service = get_services(request)

    # 使用ORM查询获取数据，包括模型使用统计
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.database.models import ApiKey, ModelUsage

    # 获取API密钥数据，包括模型使用统计
    result = await session.execute(
        select(ApiKey).options(selectinload(ApiKey.model_usages))
    )
    api_keys_data = result.scalars().all()

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
            # 对于流式响应，立即释放数据库会话，避免长时间占用
            await session.close()

            async def stream_wrapper():
                num_tokens = 0
                client_stream = await llm_service.forward_request(
                    target, req_data, headers, stream=True
                )

                async with client_stream as response:
                    async for chunk in response.aiter_text():
                        num_tokens += chunk.count(
                            'data: {"choices":[{"delta":{"content":'
                        )
                        yield chunk

                # 流式响应结束后，创建新的数据库会话来更新用量
                from app.database.database import AsyncSessionLocal

                async with AsyncSessionLocal() as new_session:
                    # 重新获取服务实例
                    _, new_api_service = get_services(request)
                    # 更新最终用量
                    await new_api_service.update_usage(
                        api_key, req_data, model, new_session
                    )
                    # 更新模型请求计数
                    await new_api_service.increment_model_reqs(
                        target_server, model, new_session
                    )
                    await new_session.commit()

            return StreamingResponse(
                stream_wrapper(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                },
            )

        # 普通响应处理
        response_text = await llm_service.forward_request(target, req_data, headers)

        try:
            response = json.loads(response_text)

            # 更新最终用量
            if "usage" in response:
                tokens = (
                    response["usage"]["prompt_tokens"]
                    + response["usage"]["completion_tokens"]
                )
                # 这里需要更新数据库中的用量
                await api_service.update_usage(api_key, req_data, model, session)

            # 更新模型请求计数
            await api_service.increment_model_reqs(target_server, model, session)

            # 提交事务
            await session.commit()

            return JSONResponse(response)
        except json.JSONDecodeError as e:
            await session.rollback()
            return JSONResponse(
                {"error": "Invalid response from upstream server", "message": str(e)},
                status_code=500,
            )

    except HTTPException as e:
        await session.rollback()
        return JSONResponse({"error": str(e.detail)}, status_code=e.status_code)
    except Exception as e:
        await session.rollback()
        return JSONResponse({"error": "Internal server error"}, status_code=500)


@router.post("/v1/embeddings")
@router.post("/embeddings")
async def proxy_handler_embeddings(
    request: Request, session: AsyncSession = Depends(get_db_session)
):
    """处理embeddings请求转发"""
    llm_service, api_service = get_services(request)

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

        # 更新用量（embedding模型使用系数0.1）
        if "usage" in response and "total_tokens" in response["usage"]:
            await api_service.update_usage(api_key, req_data, model, session)

        # 更新模型请求计数
        await api_service.increment_model_reqs(target_server, model, session)

        # 提交事务
        await session.commit()

        return JSONResponse(response)

    except json.JSONDecodeError as e:
        await session.rollback()
        return JSONResponse(
            {"error": "Invalid response from upstream server", "message": str(e)},
            status_code=500,
        )
    except HTTPException as e:
        await session.rollback()
        return JSONResponse({"error": str(e.detail)}, status_code=e.status_code)
    except Exception as e:
        await session.rollback()
        return JSONResponse({"error": "Internal server error"}, status_code=500)


@router.post("/v1/completions")
@router.post("/completions")
async def proxy_handler_completions(
    request: Request, session: AsyncSession = Depends(get_db_session)
):
    """请求转发处理"""
    llm_service, api_service = get_services(request)

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
            # 对于流式响应，立即释放数据库会话，避免长时间占用
            await session.close()

            async def stream_wrapper():
                client_stream = await llm_service.forward_request(
                    target, req_data, headers, stream=True
                )

                async with client_stream as response:
                    async for chunk in response.aiter_text():
                        yield chunk

                # 流式响应结束后，创建新的数据库会话来更新用量
                from app.database.database import AsyncSessionLocal

                async with AsyncSessionLocal() as new_session:
                    # 重新获取服务实例
                    _, new_api_service = get_services(request)
                    # 更新Anthropic使用统计
                    await new_api_service.update_anthropic_usage(
                        api_key, model, new_session
                    )
                    # 更新模型请求计数
                    await new_api_service.increment_model_reqs(
                        target_server, model, new_session
                    )
                    await new_session.commit()

            return StreamingResponse(
                stream_wrapper(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                },
            )

        # 普通响应处理
        response_text = await llm_service.forward_request(target, req_data, headers)

        try:
            response = json.loads(response_text)
            return JSONResponse(response)
        except json.JSONDecodeError as e:
            await session.rollback()
            return JSONResponse(
                {"error": "Invalid response from upstream server", "message": str(e)},
                status_code=500,
            )

    except HTTPException as e:
        await session.rollback()
        return JSONResponse({"error": str(e.detail)}, status_code=e.status_code)
    except Exception as e:
        await session.rollback()
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
            # 对于流式响应，立即释放数据库会话，避免长时间占用
            await session.close()

            async def stream_wrapper():
                client_stream = await llm_service.forward_request(
                    target, req_data, headers, stream=True
                )

                async with client_stream as response:
                    async for chunk in response.aiter_text():
                        yield chunk

                # 流式响应结束后，创建新的数据库会话来更新用量
                from app.database.database import AsyncSessionLocal

                async with AsyncSessionLocal() as new_session:
                    # 重新获取服务实例
                    _, new_api_service = get_services(request)
                    # 更新Anthropic使用统计
                    await new_api_service.update_anthropic_usage(
                        api_key, model, new_session
                    )
                    # 更新模型请求计数
                    await new_api_service.increment_model_reqs(
                        target_server, model, new_session
                    )
                    await new_session.commit()

            return StreamingResponse(
                stream_wrapper(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                },
            )

        # 普通响应处理
        response_text = await llm_service.forward_request(target, req_data, headers)

        try:
            response = json.loads(response_text)

            # 更新请求计数 - 不计算token用量，只增加reqs计数
            await api_service.update_anthropic_usage(api_key, model, session)

            # 更新模型请求计数
            await api_service.increment_model_reqs(target_server, model, session)

            # 提交事务
            await session.commit()

            return JSONResponse(response)
        except json.JSONDecodeError as e:
            await session.rollback()
            return JSONResponse(
                {"error": "Invalid response from upstream server", "message": str(e)},
                status_code=500,
            )

    except HTTPException as e:
        await session.rollback()
        return JSONResponse({"error": str(e.detail)}, status_code=e.status_code)
    except Exception as e:
        await session.rollback()
        return JSONResponse({"error": "Internal server error"}, status_code=500)
