from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class ApiKey(Base):
    """API密钥表"""
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    api_key = Column(String(64), unique=True, nullable=False, index=True)
    usage = Column(Float, default=0)
    limit_value = Column(Float, default=1000000)
    reqs = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)
    last_used = Column(DateTime, nullable=True)
    phone = Column(String(20), nullable=True)
    created_at_str = Column(String(20), nullable=True)
    last_used_str = Column(String(20), nullable=True)

    # 关系
    model_usages = relationship("ModelUsage", back_populates="api_key", cascade="all, delete-orphan")

    def to_dict(self):
        """转换为字典格式，兼容现有JSON结构"""
        return {
            "usage": self.usage,
            "limit": self.limit_value,
            "reqs": self.reqs,
            "created_at": self.created_at_str or self.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "last_used": self.last_used_str or (self.last_used.strftime("%Y-%m-%d %H:%M:%S") if self.last_used else None),
            "phone": self.phone,
            "model_usage": {mu.model_name: mu.to_dict() for mu in self.model_usages}
        }


class ModelUsage(Base):
    """模型使用统计表"""
    __tablename__ = "model_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    api_key_id = Column(Integer, ForeignKey("api_keys.id", ondelete="CASCADE"), nullable=False)
    model_name = Column(String(100), nullable=False)
    requests = Column(Integer, default=0)
    tokens = Column(Float, default=0)

    # 关系
    api_key = relationship("ApiKey", back_populates="model_usages")

    def to_dict(self):
        """转换为字典格式"""
        return {
            "requests": self.requests,
            "tokens": self.tokens
        }


class LLMServer(Base):
    """LLM服务器配置表"""
    __tablename__ = "llm_servers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    server_url = Column(String(255), unique=True, nullable=False, index=True)
    device = Column(String(100), nullable=True)
    apikey = Column(Text, nullable=True)

    # 关系
    models = relationship("ServerModel", back_populates="server", cascade="all, delete-orphan")

    def to_dict(self):
        """转换为字典格式，兼容现有JSON结构"""
        return {
            "device": self.device,
            "apikey": self.apikey,
            "model": {model.client_model_name: model.to_dict() for model in self.models}
        }


class ServerModel(Base):
    """服务器模型映射表"""
    __tablename__ = "server_models"

    id = Column(Integer, primary_key=True, autoincrement=True)
    server_id = Column(Integer, ForeignKey("llm_servers.id", ondelete="CASCADE"), nullable=False)
    client_model_name = Column(String(100), nullable=False)  # 实际后端模型名称
    actual_model_name = Column(String(100), nullable=False)  # 前端使用的模型名称
    reqs = Column(Integer, default=0)
    status = Column(Boolean, default=True)

    # 关系
    server = relationship("LLMServer", back_populates="models")

    def to_dict(self):
        """转换为字典格式"""
        return {
            "name": self.client_model_name,  # 现在返回实际后端模型名称
            "reqs": self.reqs,
            "status": self.status
        }
