"""
应用配置

集中管理应用程序的各种配置参数。
"""

import os
from typing import Optional, Literal
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """应用配置类"""

    # OpenAI 配置
    openai_api_key: str = ""
    openai_api_base: str = "https://api.openai.com/v1"
    default_model: str = "gpt-4o-mini"

    # 嵌入模型配置
    embedding_provider: Literal["openai",
                                "dashscope", "huggingface", "ollama"] = "openai"
    embedding_model: str = "text-embedding-ada-002"
    embedding_api_key: str = ""  # 留空则使用 openai_api_key
    embedding_api_base: str = ""  # 留空则使用 openai_api_base

    # 向量数据库配置
    chroma_persist_directory: str = "./data/chroma_db"

    # 记忆配置
    memory_file: str = "./data/memory/long_term_memory.json"
    max_memories_to_retrieve: int = 5

    # 试题生成配置
    max_revisions: int = 3
    default_question_count: int = 5

    # 日志配置
    log_level: str = "INFO"

    # ASR 语音识别配置
    asr_api_base: str = "http://172.168.0.200:8889/v1"
    asr_api_key: str = "EMPTY"
    asr_model: str = "Qwen/Qwen2-Audio-7B-Instruct"

    # 多源检索配置
    tavily_api_key: str = ""

    # Reranker 配置
    reranker_provider: Literal["none", "cohere", "huggingface", "llm"] = "none"
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    cohere_api_key: str = ""

    # Browser Agent 配置
    browser_headless: bool = True
    browser_timeout: int = 30000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """获取配置实例（单例）"""
    return Settings()


# 导出常用配置
settings = get_settings()


def get_llm_config() -> dict:
    """获取 LLM 配置"""
    return {
        "api_key": settings.openai_api_key or os.getenv("OPENAI_API_KEY", ""),
        "base_url": settings.openai_api_base,
        "default_model": settings.default_model
    }


def get_embedding_config() -> dict:
    """获取嵌入模型配置"""
    config = {
        "provider": settings.embedding_provider,
        "model": settings.embedding_model,
    }

    # 根据不同 provider 设置不同的配置
    if settings.embedding_provider == "openai":
        config["api_key"] = settings.embedding_api_key or settings.openai_api_key or os.getenv(
            "OPENAI_API_KEY", "")
        config["base_url"] = settings.embedding_api_base or settings.openai_api_base
    elif settings.embedding_provider == "dashscope":
        # 阿里云灵积（通义）
        config["api_key"] = settings.embedding_api_key or os.getenv(
            "DASHSCOPE_API_KEY", "")
    elif settings.embedding_provider == "huggingface":
        # HuggingFace 本地模型
        config["model_name"] = settings.embedding_model
    elif settings.embedding_provider == "ollama":
        # Ollama 本地模型
        config["base_url"] = settings.embedding_api_base or "http://localhost:11434"
        config["model"] = settings.embedding_model

    return config


def get_llm(model: str = None, temperature: float = 0, **kwargs):
    """
    获取配置好的 LLM 实例

    Args:
        model: 模型名称，默认使用配置文件中的 default_model
        temperature: 温度参数
        **kwargs: 其他传递给 ChatOpenAI 的参数

    Returns:
        ChatOpenAI 实例
    """
    from langchain_openai import ChatOpenAI

    model_name = model or settings.default_model
    api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY", "")
    base_url = settings.openai_api_base

    return ChatOpenAI(
        model=model_name,
        temperature=temperature,
        openai_api_key=api_key,
        openai_api_base=base_url,
        **kwargs
    )


def get_asr_client():
    """
    获取 ASR 语音识别服务客户端

    返回 OpenAI-compatible 客户端，指向 vllm ASR 服务。

    Returns:
        OpenAI 客户端实例
    """
    from openai import OpenAI
    return OpenAI(
        api_key=settings.asr_api_key or "EMPTY",
        base_url=settings.asr_api_base,
    )


def get_tavily_config() -> dict:
    """获取 Tavily 搜索配置"""
    return {
        "api_key": settings.tavily_api_key or os.getenv("TAVILY_API_KEY", ""),
    }


def get_reranker_config() -> dict:
    """获取 Reranker 配置"""
    return {
        "provider": settings.reranker_provider,
        "model": settings.reranker_model,
        "cohere_api_key": settings.cohere_api_key or os.getenv("COHERE_API_KEY", ""),
    }


def get_browser_config() -> dict:
    """获取 Browser Agent 配置"""
    return {
        "headless": settings.browser_headless,
        "timeout": settings.browser_timeout,
    }
