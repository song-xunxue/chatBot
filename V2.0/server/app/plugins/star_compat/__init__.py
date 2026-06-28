"""
.star 兼容层(M6)
加载 AstrBot 风格 .star 插件(@filter 装饰器 + Star 子类 + @llm_tool),适配到 V2.0
EventBus / ToolRegistry。子集兼容(docs/04 §8.3 限制与降级):

适配(@filter → V2.0 钩子):
  @command(name)/@regex(pattern)  → on_message_in(前缀/正则匹配,命中则调 handler+STOP 跳过 LLM)
  @on_llm_request                  → on_before_llm
  @on_llm_response                 → on_after_llm
  @after_message_sent              → on_message_out
  @llm_tool(name)                  → ToolRegistry 注册(M5 tool-loop 调用)

不兼容(静默跳过/降级):群聊/@/频道事件、AstrBotContext 深度 API(get_provider_by_id/
Config/Platform 等)、指令组级联。依赖这些的 .star 插件加载失败隔离(不影响其他)。

机制:轻量 astrbot 兼容包(star_compat/astrbot/,同名 API 子集)——StarLoader 把 star_compat/
加入 sys.path,使 .star 插件 `import astrbot` 命中兼容包(而非 V2.0/Ref/AstrBot 真包)。

作者: 李文煜
日期: 2026-06-28
"""
