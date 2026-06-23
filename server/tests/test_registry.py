"""
LLM Provider 注册表测试
验证 get_provider 的实例化/key 注入/大小写/未知异常，available_providers 的有/无 key 分支

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M2 验证：覆盖 registry 全部接口与各 provider 配置
"""
import pytest

from llm.registry import get_provider, available_providers
from llm.glm import GLMProvider
from llm.deepseek import DeepSeekProvider
from llm.siliconflow import SiliconFlowProvider
from llm.openai_compat import OpenAICompatProvider
from core.config import settings


def test_get_provider_glm_injects_key():
    p = get_provider("glm")
    assert isinstance(p, GLMProvider)
    assert p.api_key == settings.glm_api_key


def test_get_provider_case_insensitive():
    assert isinstance(get_provider("GLM"), GLMProvider)
    assert isinstance(get_provider("DeepSeek"), DeepSeekProvider)
    assert isinstance(get_provider("SILICONFLOW"), SiliconFlowProvider)


def test_get_provider_all_are_openai_compat():
    for name in ("glm", "deepseek", "siliconflow"):
        assert isinstance(get_provider(name), OpenAICompatProvider)


def test_get_provider_unknown_raises():
    with pytest.raises(ValueError):
        get_provider("nope")


def test_available_providers_empty(reset_llm_keys):
    assert available_providers() == []


def test_available_providers_with_some_keys(reset_llm_keys, monkeypatch):
    monkeypatch.setattr(settings, "glm_api_key", "k1")
    monkeypatch.setattr(settings, "siliconflow_api_key", "k2")
    assert available_providers() == ["glm", "siliconflow"]


def test_provider_static_configs():
    """校验各 provider 的 base_url / default_model 配置正确"""
    assert GLMProvider.base_url == "https://open.bigmodel.cn/api/paas/v4"
    assert GLMProvider.default_model == "glm-4-flash"
    assert DeepSeekProvider.base_url == "https://api.deepseek.com"
    assert DeepSeekProvider.default_model == "deepseek-chat"
    assert SiliconFlowProvider.base_url == "https://api.siliconflow.cn/v1"
    assert SiliconFlowProvider.default_model == "deepseek-ai/DeepSeek-V3"
