from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from datetime import datetime
from collections import defaultdict


class ModelUsage(BaseModel):
    """模型使用详情模型"""

    requests: int = Field(default=0, description="请求次数")
    tokens: float = Field(default=0, description="token使用量")


class ApiKeyUsage(BaseModel):
    """API密钥使用情况模型"""

    usage: float = Field(default=0, description="当前使用量")
    limit: float = Field(description="使用限额")
    reqs: int = Field(default=0, description="聊天请求次数")
    created_at: Optional[str] = Field(default=None, description="创建时间")
    last_used: Optional[str] = Field(default=None, description="最后使用时间")
    phone: Optional[str] = Field(default=None, description="手机号")
    model_usage: Dict[str, ModelUsage] = Field(
        default_factory=dict, description="各模型使用详情"
    )

    model_config = {"protected_namespaces": ()}


class LLMServer(BaseModel):
    """LLM服务器配置模型"""

    url: str = Field(description="服务器URL")
    model: Dict[str, str] | str | List[str] = Field(
        description="支持的模型，可以是字典(key为客户端使用的模型名，value为实际转发的模型名)、字符串或列表"
    )
    apikey: Optional[str] = Field(default=None, description="API密钥")


class AppState(BaseModel):
    """应用状态模型"""

    llm_servers: Dict[str, Dict] = Field(
        default_factory=dict, description="LLM服务器配置"
    )
    cloud_models: Dict[str, str] = Field(
        default_factory=dict, description="云端模型配置"
    )
    model_mapping: Dict[str, List] = Field(
        default_factory=lambda: defaultdict(list), description="模型到服务器的映射"
    )
    model_name_mapping: Dict[str, str] = Field(
        default_factory=dict, description="客户端模型名到实际模型名的映射"
    )
    api_usage: Dict[str, ApiKeyUsage] = Field(
        default_factory=dict, description="API使用情况"
    )

    model_config = {"protected_namespaces": ()}


class UsageStats(BaseModel):
    """使用统计模型"""

    less_than_100: int = Field(default=0, description="使用量小于100的数量")
    between_100_and_10000: int = Field(
        default=0, description="使用量在100-10000之间的数量"
    )
    more_than_10000: int = Field(default=0, description="使用量大于10000的数量")
    total_usage: float = Field(default=0, description="总使用量")
    total_entries: int = Field(default=0, description="总条目数")
    total_reqs: int = Field(default=0, description="总请求数")
    current_time: str = Field(description="当前时间")
    api_keys: List[Dict] = Field(default_factory=list, description="API密钥使用详情")
