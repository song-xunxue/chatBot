"""
插件基类 Plugin、插件上下文 PluginContext、钩子结果 HookResult、6 个钩子名常量。
钩子签名统一:async def hook(self, ctx: MessageContext) -> HookResult | None(None 视为 CONTINUE)。

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 从 V1.0 移植插件基类到 V2.0(零业务改动)
"""
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from core.config import Settings
    from plugins.manifest import PluginManifest
    from pipeline.context import MessageContext

# 6 个钩子名常量
ON_MESSAGE_IN = "on_message_in"       # 用户消息到达
ON_BEFORE_LLM = "on_before_llm"       # prompt 拼装后、调 LLM 前
ON_AFTER_LLM = "on_after_llm"         # LLM 产出后
ON_MESSAGE_OUT = "on_message_out"     # 回复发出前
ON_TICK = "on_tick"                   # 定时(调度器驱动,如 mood 衰减)
ON_DELETE = "on_delete"               # 消息标记删除(负样本)
ALL_HOOKS = (ON_MESSAGE_IN, ON_BEFORE_LLM, ON_AFTER_LLM, ON_MESSAGE_OUT, ON_TICK, ON_DELETE)


class HookResult:
    """钩子返回值:CONTINUE 继续后续插件/管道;STOP 中断后续插件(及部分管道阶段)。
    用类常量而非 enum,便于插件直接 return HookResult.STOP。"""
    CONTINUE = "continue"
    STOP = "stop"


@dataclass
class PluginContext:
    """插件运行上下文:on_load 时由 Manager 注入,插件实例自存引用。
    集中提供 Redis / settings / manager 等依赖,避免插件直接耦合全局单例。"""
    manager: "object"            # PluginManager(提供 get_params / is_enabled_for 等)
    redis: "Redis"
    settings: "Settings"
    manifest: "PluginManifest"   # 本插件清单


class Plugin:
    """插件基类。子类按需覆盖 on_load/on_unload 与业务钩子。
    Manager 仅订阅 manifest.hooks 中显式声明的钩子——未声明者即使覆盖也不会被调用。"""
    manifest: "PluginManifest | None" = None
    pctx: "PluginContext | None" = None
    _alive: bool = False   # Manager 维护:on_load 成功后置 True、unload 时置 False;gate 据此跳过已卸载实例

    async def on_load(self) -> None:
        """加载钩子:读配置、连资源(子类按需覆盖)"""
        pass

    async def on_unload(self) -> None:
        """卸载钩子:释放资源(子类按需覆盖)"""
        pass

    # —— 6 个业务钩子(默认 CONTINUE,子类按需覆盖;只有 manifest 声明者会被订阅)——
    async def on_message_in(self, ctx: "MessageContext"):
        return HookResult.CONTINUE

    async def on_before_llm(self, ctx: "MessageContext"):
        return HookResult.CONTINUE

    async def on_after_llm(self, ctx: "MessageContext"):
        return HookResult.CONTINUE

    async def on_message_out(self, ctx: "MessageContext"):
        return HookResult.CONTINUE

    async def on_tick(self, ctx: "MessageContext"):
        return HookResult.CONTINUE

    async def on_delete(self, ctx: "MessageContext"):
        return HookResult.CONTINUE

    # —— 便捷方法 ——
    async def get_params(self, object_id: str) -> dict:
        """取本插件在某对象的参数:config_schema 默认值 ← 全局/按对象覆盖合并"""
        return await self.pctx.manager.get_params(self.manifest.name, object_id)
