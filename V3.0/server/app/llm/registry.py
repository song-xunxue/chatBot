"""
LLM Provider 注册表(配置驱动,2026-07-02 #7 深化)
单一注册表 _LLM_PROVIDERS(name→类/key字段/展示名),加 provider 只改一处。
get_provider / available_providers 从表查;provider_specs() 供 rest_system 生成配置状态。
深化前:get_provider 与 available_providers 各一份 if-name 名单 + rest_system._PROVIDERS 第三份——
三处按 provider 名索引的名单,加 provider 要改 3 处(浅模块负杠杆)。现归一为一份注册表。

作者: 李文煜
日期: 2026-07-02
"""
from dataclasses import dataclass

from llm.base import LLMProvider
from llm.glm import GLMProvider
from llm.deepseek import DeepSeekProvider
from llm.siliconflow import SiliconFlowProvider
from core.config import settings


@dataclass(frozen=True)
class ProviderSpec:
    """LLM provider 规格(单一注册表条目)"""
    name: str           # 内部 id(小写)
    cls: type           # Provider 类(实例化时传 api_key)
    key_attr: str       # settings 上的 api_key 字段名
    display: str        # 展示名(rest_system 面板用)


# 唯一注册表:加 provider 只在此添一条(get_provider/available_providers/rest_system 全自动跟上)
_LLM_PROVIDERS: list[ProviderSpec] = [
    ProviderSpec("glm", GLMProvider, "glm_api_key", "GLM(智谱)"),
    ProviderSpec("deepseek", DeepSeekProvider, "deepseek_api_key", "DeepSeek"),
    ProviderSpec("siliconflow", SiliconFlowProvider, "siliconflow_api_key", "硅基流动"),
]
_BY_NAME: dict[str, ProviderSpec] = {p.name: p for p in _LLM_PROVIDERS}


def get_provider(name: str) -> LLMProvider:
    """按 provider 名实例化(从 settings 注入对应 api_key);未知名抛 ValueError。
    供 llm/resolver.py(#1)与 pipeline/stages.py 直接调用。"""
    spec = _BY_NAME.get((name or "").lower())
    if not spec:
        raise ValueError(f"未知 LLM provider: {name}")
    return spec.cls(api_key=getattr(settings, spec.key_attr))


def available_providers() -> list[str]:
    """已配置 api_key 的 provider 名(用于无 key 时降级/提示;供 resolver.is_provider_available)"""
    return [p.name for p in _LLM_PROVIDERS if getattr(settings, p.key_attr)]


def provider_specs() -> list[ProviderSpec]:
    """所有 provider 规格(rest_system 从此生成配置状态,不再维护第三份名单)"""
    return list(_LLM_PROVIDERS)
