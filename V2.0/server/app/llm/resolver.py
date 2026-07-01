"""
LLM provider 解析归属模块(2026-07-02,架构 #1)
owns "按任务解析 provider 名 + 是否可用 + 实例化"——统一此前 score / reverse_infer / memory 三处
各自 `or` 链 + 不一致 key 判断的发散兜底。调用方不再各自决定降级策略。

解析链(全任务统一):override(调用方显式传入)→ 任务专用设定 → 全局 chat_provider;
key 未配则 resolve_provider 返 None(调用方据此降级,不抛)。

作者: 李文煜
日期: 2026-07-02
"""
from llm.registry import get_provider, available_providers
from core.config import settings


def _task_setting(task: str) -> str:
    """任务 → 该任务的专用 provider 设定(空=该任务无专用,回退 chat_provider)。
    运行时读 settings(支持 /system/reload 热更新)。"""
    return {
        "chat": "",                                # 聊天直接用 chat_provider(persona 覆盖经 override 传入)
        "score": settings.score_provider,
        "reverse_infer": settings.reverse_infer_provider,
        "memory": settings.memory_summary_provider,
    }.get(task, "")


def resolve_provider_name(task: str, override: str = "") -> str:
    """解析某任务用的 provider 名(统一兜底链):override → 任务专用设定 → chat_provider。
    仅决定名字,不做 key 存在判断(用 is_provider_available / resolve_provider 决定降级)。"""
    name = (override or "").strip()
    if not name:
        name = (_task_setting(task) or "").strip()
    if not name:
        name = (settings.chat_provider or "").strip()
    return name


def is_provider_available(name: str) -> bool:
    """provider 名非空 且 已配 key(在 available_providers 里)"""
    return bool(name) and name in available_providers()


def resolve_provider(task: str, override: str = ""):
    """解析 + 实例化:名走 resolve_provider_name;key 未配返 None(调用方据此降级,不抛)。
    统一兜底链 + 一致 key 判断,替代各调用方散落的 or 链与 try/except。"""
    name = resolve_provider_name(task, override)
    if not is_provider_available(name):
        return None
    return get_provider(name)
