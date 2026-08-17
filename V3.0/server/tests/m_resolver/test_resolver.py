"""
provider resolver 单测(2026-07-02,架构 #1)
覆盖统一解析链(override→任务设定→chat_provider)、可用性判断、级联降级、各任务专用设定。
固化"一条规则一个归属",防止再退化成 6 处各自 or 兜底。

作者: 李文煜
日期: 2026-07-02
"""
from llm.resolver import resolve_provider_name, is_provider_available, resolve_provider
from llm.glm import GLMProvider
from llm.deepseek import DeepSeekProvider
from core.config import settings


def _keys(monkeypatch, **on):
    """控制 available_providers:先把三个 key 全清(conftest 已清,再保险),再按需开。"""
    for k in ("glm", "deepseek", "siliconflow"):
        monkeypatch.setattr(settings, f"{k}_api_key", "")
    for k, v in on.items():
        monkeypatch.setattr(settings, f"{k}_api_key", v)


# —— resolve_provider_name: 兜底链顺序 ——
def test_name_override_wins(monkeypatch):
    monkeypatch.setattr(settings, "chat_provider", "glm")
    monkeypatch.setattr(settings, "score_provider", "deepseek")
    assert resolve_provider_name("score", "siliconflow") == "siliconflow"


def test_name_task_setting_next(monkeypatch):
    monkeypatch.setattr(settings, "chat_provider", "glm")
    monkeypatch.setattr(settings, "score_provider", "deepseek")
    assert resolve_provider_name("score") == "deepseek"


def test_name_chat_provider_fallback(monkeypatch):
    monkeypatch.setattr(settings, "chat_provider", "glm")
    monkeypatch.setattr(settings, "score_provider", "")
    assert resolve_provider_name("score") == "glm"


def test_name_chat_task(monkeypatch):
    monkeypatch.setattr(settings, "chat_provider", "deepseek")
    assert resolve_provider_name("chat") == "deepseek"


# —— is_provider_available ——
def test_available(monkeypatch):
    _keys(monkeypatch, deepseek="k")
    assert is_provider_available("deepseek") is True
    assert is_provider_available("glm") is False      # 无 key
    assert is_provider_available("") is False


# —— resolve_provider: 实例化 + 降级 ——
def test_resolve_returns_instance(monkeypatch):
    _keys(monkeypatch, deepseek="k")
    monkeypatch.setattr(settings, "chat_provider", "deepseek")
    assert isinstance(resolve_provider("chat"), DeepSeekProvider)


def test_resolve_none_when_no_key(monkeypatch):
    """key 全未配 → None(不抛,调用方降级)"""
    _keys(monkeypatch)
    monkeypatch.setattr(settings, "chat_provider", "deepseek")
    assert resolve_provider("chat") is None


def test_reverse_infer_empty_setting_falls_to_chat_name(monkeypatch):
    """reverse_infer_provider 空 → 名字链回退 chat_provider(此前 reverse_infer 不回退,会静默 abort)"""
    monkeypatch.setattr(settings, "reverse_infer_provider", "")
    monkeypatch.setattr(settings, "chat_provider", "deepseek")
    assert resolve_provider_name("reverse_infer") == "deepseek"


def test_reverse_infer_unavailable_returns_none(monkeypatch):
    """reverse_infer_provider 配了但无 key → None(不抛,调用方 abort)。
    名字级解析统一即可;不做"可用性级联"(避免静默用别的模型跑反推,结果不可控)"""
    _keys(monkeypatch, deepseek="k")
    monkeypatch.setattr(settings, "reverse_infer_provider", "glm")   # glm 无 key
    monkeypatch.setattr(settings, "chat_provider", "deepseek")
    assert resolve_provider("reverse_infer") is None


def test_memory_uses_memory_summary_provider(monkeypatch):
    _keys(monkeypatch, glm="k")
    monkeypatch.setattr(settings, "memory_summary_provider", "glm")
    monkeypatch.setattr(settings, "chat_provider", "deepseek")
    assert isinstance(resolve_provider("memory"), GLMProvider)


def test_score_uses_override_then_setting(monkeypatch):
    _keys(monkeypatch, siliconflow="k", deepseek="k")
    monkeypatch.setattr(settings, "score_provider", "deepseek")
    monkeypatch.setattr(settings, "chat_provider", "glm")
    assert resolve_provider_name("score", "siliconflow") == "siliconflow"  # override 优先
    assert resolve_provider_name("score") == "deepseek"                     # 无 override→任务设定
