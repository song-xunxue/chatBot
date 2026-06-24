"""
hello 示例插件（M4.2）
演示完整生命周期：on_load 记实例状态、on_after_llm 在回复末尾追加后缀。
由 _template/ 改造而来，默认关闭，用于端到端验证插件系统可用。

作者: 李文煜
日期: 2026-06-24
"""
from plugins.base import Plugin, HookResult


class HelloPlugin(Plugin):
    """示例插件：on_after_llm 追加后缀"""

    async def on_load(self) -> None:
        # 演示插件实例可持有运行时状态
        self._loaded = True

    async def on_after_llm(self, ctx):
        params = await self.get_params(ctx.object_id)
        suffix = params.get("suffix", "[hello]")
        if ctx.reply_text:
            ctx.reply_text = f"{ctx.reply_text} {suffix}"
        return HookResult.CONTINUE
