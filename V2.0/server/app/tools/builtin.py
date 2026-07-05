"""
自研工具(M5):get_persona / write_memory / reverse_infer_trigger / web_search(DuckDuckGo)。
对应 docs/01 §6 自研工具清单(get_persona/write_memory/reverse_infer_trigger/联网兜底)。

作者: 李文煜
日期: 2026-06-28

2026-06-28
变更说明:
  1. M5 新建自研工具:人设查询/记忆写入/反推触发/DuckDuckGo联网 + register_builtin_tools
"""
import json

import httpx

from tools.base import Tool, ToolRegistry


class GetPersonaTool(Tool):
    """查询当前聊天对象的人设(性格/说话风格/背景),供 LLM 回归人设时参考"""
    name = "get_persona"
    description = ("查询当前聊天对象的虚拟角色人设(性格/说话风格/背景/口头禅)。"
                   "当需要确认自己扮演谁、如何符合人设回答时调用。")
    parameters = {"type": "object", "properties": {}}

    async def execute(self, args: dict, ctx) -> str:
        from persona.store import get_object_persona_id, get_persona
        from persona.renderer import render_system_prompt
        pid = await get_object_persona_id(ctx.redis, ctx.object_id)
        card = await get_persona(ctx.redis, pid)
        if card is None:
            return "(无绑定人设)"
        return render_system_prompt(card, card.dynamic_state)[:600]


class WriteMemoryTool(Tool):
    """把一条值得长期记住的事实/偏好写入长期记忆"""
    name = "write_memory"
    description = ("把一条值得长期记住的关于用户的事实/偏好/关系/事件写入长期记忆。"
                   "当用户透露重要信息时调用。")
    parameters = {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "记忆内容(简短陈述)"},
            "category": {"type": "string", "description": "类别:fact/preference/relationship/event/personality", "default": "fact"},
            "importance": {"type": "number", "description": "重要性 0-1,默认 0.5", "default": 0.5},
        },
        "required": ["content"],
    }

    async def execute(self, args: dict, ctx) -> str:
        from memory.coordinator import MemoryCoordinator
        from memory.models import Category
        content = (args.get("content") or "").strip()
        if not content:
            return "(content 为空,未写入)"
        try:
            cat = Category(args.get("category", "fact"))
        except ValueError:
            cat = Category.FACT
        importance = max(0.0, min(1.0, float(args.get("importance", 0.5))))
        # 走 coordinator 的公开 upsert_fact(架构 #6 收口):不再访问私有 _upsert_fact_dedup/_lock。
        # 用 ctx.redis 实例化(pipeline 注入,与当前会话同源 redis;测试隔离);无状态单条写不需单例生命周期
        redis = ctx.redis
        if redis is None:
            return "(记忆系统不可用)"
        coord = MemoryCoordinator(redis, llm_provider=None)
        await coord.upsert_fact(ctx.object_id, {
            "content": content, "category": cat.value,
            "importance": importance, "emotion": 0.0,
        })
        return f"已写入记忆: {content}"


class ReverseInferTool(Tool):
    """触发人设反推预览(dry_run,不直接改人设),返回建议 diff"""
    name = "reverse_infer_trigger"
    description = ("触发人设反推预览:从近期评分正/负样本提炼人设字段调整建议(dry_run,仅预览不落库)。"
                   "当怀疑人设需要校准、或管理员要求时调用。")
    parameters = {"type": "object", "properties": {}}

    async def execute(self, args: dict, ctx) -> str:
        from score.reverse_infer import infer_and_merge
        res = await infer_and_merge(ctx.redis, ctx.object_id, dry_run=True)
        if "confirm_token" in res:
            return json.dumps({
                "diff": res["diff"],
                "positive_count": res["positive_count"],
                "negative_count": res["negative_count"],
                "confirm_token": res["confirm_token"],
            }, ensure_ascii=False)
        return f"反推中止: {res.get('aborted_reason')}"


class WebSearchTool(Tool):
    """联网搜索(DuckDuckGo Instant Answer API,无 key),返回若干条摘要结果"""
    name = "web_search"
    description = ("联网搜索实时信息/外部知识(DuckDuckGo)。"
                   "当需要查询你不知道的实时事实、新闻、外部知识时调用。")
    parameters = {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "搜索关键词"}},
        "required": ["query"],
    }

    async def execute(self, args: dict, ctx) -> str:
        query = (args.get("query") or "").strip()
        if not query:
            return "(空查询)"
        try:
            # DuckDuckGo Instant Answer API(JSON,无 key,no_html 去标签)
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get("https://api.duckduckgo.com/", params={
                    "q": query, "format": "json", "no_html": "1", "no_redirect": "1",
                    "skip_disambig": "1",
                })
                data = resp.json()
        except Exception as e:
            return f"(搜索失败: {e})"
        results = []
        if data.get("AbstractText"):
            results.append({"title": data.get("Heading", ""),
                            "text": data["AbstractText"],
                            "url": data.get("AbstractURL", "")})
        for t in data.get("RelatedTopics", [])[:8]:
            if isinstance(t, dict) and t.get("Text"):
                results.append({"text": t["Text"], "url": t.get("FirstURL", "")})
            elif isinstance(t, dict) and isinstance(t.get("Topics"), list):
                # 嵌套分类(如人物/概念),取前 2 条子项
                for sub in t["Topics"][:2]:
                    if isinstance(sub, dict) and sub.get("Text"):
                        results.append({"text": sub["Text"]})
        if not results:
            return f"(无搜索结果: {query})"
        return json.dumps(results[:5], ensure_ascii=False)


def register_builtin_tools(registry: ToolRegistry, *, web_search_enable: bool = True) -> None:
    """注册自研工具到 registry(lifespan 启动时调用)"""
    registry.register(GetPersonaTool())
    registry.register(WriteMemoryTool())
    registry.register(ReverseInferTool())
    if web_search_enable:
        registry.register(WebSearchTool())
