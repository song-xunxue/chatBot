"""
LLM registry 配置驱动单测(2026-07-02,#7 深化)
钉死:单一注册表 _LLM_PROVIDERS 驱动 get_provider/available_providers/provider_specs;
加 provider 只在此添一条,三处自动跟上(消除此前三份散落名单)。
modality/registry 由 tests/m_vision 覆盖(此处不重复)。

作者: 李文煜
日期: 2026-07-02
"""
import pytest

from llm.registry import get_provider, available_providers, provider_specs, ProviderSpec
from llm.glm import GLMProvider
from llm.deepseek import DeepSeekProvider
from llm.siliconflow import SiliconFlowProvider
from core.config import settings


def _keys(monkeypatch, **on):
    for k in ("glm", "deepseek", "siliconflow"):
        monkeypatch.setattr(settings, f"{k}_api_key", "")
    for k, v in on.items():
        monkeypatch.setattr(settings, f"{k}_api_key", v)


def test_get_provider_by_name(monkeypatch):
    """按名实例化对应类(大小写不敏感)"""
    _keys(monkeypatch, glm="g", deepseek="d", siliconflow="s")
    assert isinstance(get_provider("glm"), GLMProvider)
    assert isinstance(get_provider("DeepSeek"), DeepSeekProvider)   # 大小写不敏感
    assert isinstance(get_provider("siliconflow"), SiliconFlowProvider)


def test_get_provider_unknown_raises():
    with pytest.raises(ValueError):
        get_provider("xxx")


def test_available_providers_reflects_keys(monkeypatch):
    """available_providers 只列已配 key 的"""
    _keys(monkeypatch, deepseek="d")
    assert available_providers() == ["deepseek"]
    _keys(monkeypatch)   # 全清
    assert available_providers() == []


def test_provider_specs_shape():
    """单一注册表 = 三条规格,字段齐(name/cls/key_attr/display)"""
    specs = provider_specs()
    assert {s.name for s in specs} == {"glm", "deepseek", "siliconflow"}
    assert all(isinstance(s, ProviderSpec) for s in specs)
    assert all(s.cls and s.key_attr and s.display for s in specs)


def test_single_registry_drives_all(monkeypatch):
    """不变量:_LLM_PROVIDERS 一份名单驱动 get_provider + available_providers + provider_specs
    (加 provider 只在 _LLM_PROVIDERS 添一条,三处自动跟上,无需改多处)"""
    from llm.registry import _LLM_PROVIDERS
    _keys(monkeypatch, glm="g", deepseek="d", siliconflow="s")
    names_in_table = {s.name for s in _LLM_PROVIDERS}
    names_resolvable = {s.name for s in _LLM_PROVIDERS if get_provider(s.name)}   # 每条都能实例化
    assert names_resolvable == names_in_table
    assert names_in_table == {s.name for s in provider_specs()}
