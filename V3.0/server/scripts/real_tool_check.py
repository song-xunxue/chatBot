"""
真实 GLM tool-loop 验证(M5 一次性脚本)
用 fakeredis + 真 GLM + 自研工具(get_persona/write_memory/web_search),验证 tool-loop 端到端:
  1. 联网场景:LLM 决策调 web_search(DuckDuckGo)→ 看结果 → 回复
  2. 记忆场景:LLM 决策调 write_memory 写入长期记忆
确认 function calling + tool-loop + 自研工具在真实 LLM 下工作。

作者: 李文煜
日期: 2026-06-28
"""
import sys
import asyncio
import logging
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

# 开 INFO 日志,看 tool-loop 调用了哪些工具
logging.basicConfig(level=logging.INFO, format="%(message)s")

import fakeredis

import storage.redis_client as redis_client
from core.config import settings
from persona.store import set_persona, bind_object_persona
from persona.models import PersonaCard
from mood import service as mood_service
from llm.registry import get_provider
from tools import get_tool_registry, register_builtin_tools
from tools.base import ToolContext
from pipeline.tool_loop import run_tool_loop


async def main():
    fake = fakeredis.FakeAsyncRedis(decode_responses=True)
    redis_client._redis = fake
    settings.tool_loop_enable = True
    card = PersonaCard(id="p1", name="小晴",
                       creator_notes="我是小晴,性格温柔慵懒,爱用叠词,喜欢和用户聊天。可调用工具帮助用户。")
    await set_persona(fake, card)
    await bind_object_persona(fake, "u1", "p1")
    await mood_service.seed_default_kinds(fake)

    provider = get_provider("glm")
    registry = get_tool_registry()
    register_builtin_tools(registry, web_search_enable=True)
    tctx = ToolContext(redis=fake, object_id="u1")
    system_prompt = ("你是小晴,一个温柔的角色。需要时可调用工具:web_search 联网查实时信息,"
                     "write_memory 记住用户的的重要信息,get_persona 查自己人设。")

    cases = [
        ("联网搜索", "帮我查一下 Python 编程语言是什么"),
        ("写入记忆", "我叫林晓,养了一只橘猫叫橘子,请你记住"),
    ]
    for name, user_text in cases:
        print(f"\n=== {name} ===")
        print(f"[user] {user_text}")
        reply = await run_tool_loop(provider, system_prompt, user_text, [], registry, tctx,
                                    model="glm-4-flash", max_iterations=4)
        print(f"[ai] {reply}")

    # 验证记忆已写入
    from memory import store
    items = await store.get_all_long_term(fake, "u1")
    print(f"\n=== long-term 记忆({len(items)} 条)===")
    for m in items:
        print(f"  [{m.category.value}] {m.content}")


if __name__ == "__main__":
    asyncio.run(main())
