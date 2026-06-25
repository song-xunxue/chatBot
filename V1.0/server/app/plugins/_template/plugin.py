"""
插件开发模板 —— 复制本目录、改 name 与钩子实现即可（本目录以 _ 开头，不会被自动加载）。
演示：on_after_llm 在回复末尾追加标签（读取 config_schema.tag 默认值，可按对象覆盖）。

作者: 李文煜
日期: 2026-06-24
"""
from plugins.base import Plugin, HookResult


class TemplatePlugin(Plugin):
    """模板插件：on_after_llm 追加标签"""

    async def on_load(self) -> None:
        # 加载时读配置、连资源（此处仅占位演示）
        pass

    async def on_after_llm(self, ctx):
        # 取本插件在此对象的参数（config_schema 默认值 ← 按对象覆盖）
        params = await self.get_params(ctx.object_id)
        tag = params.get("tag", "[template]")
        if tag and ctx.reply_text:
            ctx.reply_text = f"{ctx.reply_text}\n{tag}"
        return HookResult.CONTINUE
