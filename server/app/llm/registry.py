"""
LLM Provider 注册表
按 provider 名实例化对应实现，从 settings 注入 api_key；并提供"已配置 key 的可用 provider"查询，
用于无 key 时的降级提示。

作者: 李文煜
日期: 2026-06-19

2026-06-19
变更说明：
  1. M2.1 创建 registry：get_provider 按名实例化 + available_providers 列出可用项
"""
from llm.base import LLMProvider
from llm.glm import GLMProvider
from llm.deepseek import DeepSeekProvider
from llm.siliconflow import SiliconFlowProvider
from core.config import settings


def get_provider(name: str) -> LLMProvider:
    """按 provider 名实例化（注入对应 api_key）；未知名抛 ValueError"""
    name = name.lower()
    if name == "glm":
        return GLMProvider(api_key=settings.glm_api_key)
    if name == "deepseek":
        return DeepSeekProvider(api_key=settings.deepseek_api_key)
    if name == "siliconflow":
        return SiliconFlowProvider(api_key=settings.siliconflow_api_key)
    raise ValueError(f"未知 LLM provider: {name}")


def available_providers() -> list[str]:
    """返回已配置 api_key 的 provider 名（用于无 key 时降级/提示）"""
    result = []
    if settings.glm_api_key:
        result.append("glm")
    if settings.deepseek_api_key:
        result.append("deepseek")
    if settings.siliconflow_api_key:
        result.append("siliconflow")
    return result
