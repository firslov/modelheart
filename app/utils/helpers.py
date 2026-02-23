import random
import re
import string
import json
import aiofiles
from typing import Dict, Any, Union
from datetime import datetime
from app.config.settings import settings
from app.utils.logging_config import setup_logging, get_logger

# 初始化日志配置
setup_logging(level="INFO")
logger = get_logger(__name__)


async def load_json_file(filename: str) -> Dict:
    """异步加载JSON文件

    Args:
        filename: JSON文件路径

    Returns:
        Dict: 加载的JSON数据
    """
    try:
        async with aiofiles.open(filename, "r") as f:
            return json.loads(await f.read())
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Error loading {filename}: {str(e)}")
        return {}


async def save_json_file(data: Dict, filename: str) -> None:
    """异步保存JSON文件

    Args:
        data: 要保存的数据
        filename: 保存的文件路径
    """
    try:
        async with aiofiles.open(filename, "w") as f:
            await f.write(json.dumps(data, indent=2))
    except Exception as e:
        logger.error(f"Error saving {filename}: {str(e)}")
        raise


def generate_token(prefix: str = "xh", length: int = 20) -> str:
    """生成随机API密钥

    Args:
        prefix: 密钥前缀
        length: 密钥长度

    Returns:
        str: 生成的API密钥
    """
    return f"{prefix}-" + "".join(
        random.choices(string.digits + string.ascii_letters, k=length)
    )


def get_current_time() -> str:
    """获取当前北京时间

    Returns:
        str: 格式化的时间字符串
    """
    return datetime.now(settings.TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")


def log_api_usage(api_key: str, usage_info: Dict) -> None:
    """记录API使用情况

    Args:
        api_key: API密钥
        usage_info: 使用情况信息
    """
    remaining = usage_info.get('limit', 0) - usage_info.get('usage', 0)
    logger.info(
        f"API key={api_key[-6:]} | "
        f"remaining={remaining} | "
        f"requests={usage_info.get('reqs', 0)}"
    )


def sanitize_anthropic_system_text(text: str) -> str:
    """清理 Anthropic system 文本中的缓存干扰内容

    移除导致缓存失效的内容：
    - x-anthropic-billing-header: ... (包含动态变化的 cch 值)
    - 规范化多余的连续空格

    Args:
        text: 原始 system 文本

    Returns:
        str: 清理后的文本
    """
    if not text:
        return text

    # 移除 x-anthropic-billing-header 整行（可能以换行符结尾或在文本中间）
    # 匹配模式: x-anthropic-billing-header: ... (直到分号或换行)
    text = re.sub(
        r'x-anthropic-billing-header:\s*[^;\n]+;?\s*',
        '',
        text
    )

    # 规范化连续多个空格为单个空格（保留换行符）
    text = re.sub(r'[ \t]+', ' ', text)

    # 移除行首行尾的多余空格
    lines = text.split('\n')
    lines = [line.strip() for line in lines]
    text = '\n'.join(lines)

    # 移除多余的空行（超过2个连续空行压缩为1个）
    text = re.sub(r'\n{3,}', '\n\n', text)

    # 移除首尾空白
    text = text.strip()

    return text


def sanitize_anthropic_request(req_data: Dict[str, Any]) -> Dict[str, Any]:
    """清理 Anthropic 请求中的缓存干扰内容

    处理 system 字段（可能是字符串或对象数组）

    Args:
        req_data: 原始请求数据

    Returns:
        Dict: 清理后的请求数据
    """
    if not req_data:
        return req_data

    # 处理顶级 system 字段
    if 'system' in req_data:
        system = req_data['system']

        if isinstance(system, str):
            # system 是字符串，直接清理
            req_data['system'] = sanitize_anthropic_system_text(system)

        elif isinstance(system, list):
            # system 是对象数组，清理每个对象的 text 字段
            for item in system:
                if isinstance(item, dict) and 'text' in item:
                    item['text'] = sanitize_anthropic_system_text(item['text'])

    return req_data
