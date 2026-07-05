"""
tool-loop 引擎(M5)
LLM + tools → function calling 决策 tool_calls → 执行工具 → 结果回填 → 再推理(循环,
最多 max_iterations 轮防死循环)。借鉴 AstrBot tool-loop。非流式(QQ 场景累积完整回复再下发)。

作者: 李文煜
日期: 2026-06-28

2026-06-28
变更说明:
  1. M5 新建 tool-loop 引擎:run_tool_loop(chat_with_tools→tool_calls→执行→回填→再推理)
"""
import logging

from llm.json_extract import extract_json_object
from tools.base import ToolContext

logger = logging.getLogger(__name__)


async def run_tool_loop(provider, system_prompt: str, user_text: str,
                        history_messages: list, registry, tctx: ToolContext, *,
                        model: str = "", max_iterations: int = 5) -> str:
    """tool-loop 主循环,返回最终回复文本。
    provider:需支持 chat_with_tools(OpenAICompatProvider 及子类)。
    history_messages:list[Message](对话历史,转 dict 拼 payload)。
    registry:ToolRegistry(提供 openai_tools + call)。tctx:ToolContext(redis+object_id)。
    无工具调用或达上限时返回最后一段文本。"""
    tools_schema = registry.openai_tools()
    # 构造 payload messages(system + 历史 + 本次 user)
    msgs: list[dict] = [{"role": "system", "content": system_prompt}]
    msgs += [{"role": m.role, "content": m.content} for m in history_messages]
    msgs.append({"role": "user", "content": user_text})
    last_text = ""
    logger.info("tool-loop 启动 provider=%s iterations=%d", type(provider).__name__, max_iterations)
    for i in range(max_iterations):
        try:
            resp = await provider.chat_with_tools(msgs, model=model, tools=tools_schema)
        except Exception as e:
            # LLM 调用失败(如 provider 限流 429):有已产出文本则用它,否则重抛由 stage_tool_loop 兜底
            # 绝不把错误堆栈当回复发给用户(bug 修复:此前 return f"(工具循环调用失败: {e})" 会直发 QQ)
            logger.warning("tool-loop LLM 调用失败(iter %d, provider=%s): %s",
                           i, type(provider).__name__, e)
            if last_text:
                return last_text
            raise
        last_text = resp.text
        if not resp.tool_calls:
            return resp.text                    # 无工具调用 → 最终回复
        # 有 tool_calls:追加 assistant(tool_calls)+ 执行每个工具 + 追加 tool 结果
        msgs.append({
            "role": "assistant",
            "content": resp.text or "",
            "tool_calls": [
                {"id": tc["id"], "type": "function",
                 "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                for tc in resp.tool_calls
            ],
        })
        for tc in resp.tool_calls:
            args = extract_json_object(tc["arguments"]) or {}
            try:
                result = await registry.call(tc["name"], args, tctx)
                logger.info("tool-loop 调用工具 %s args=%s → %s",
                            tc["name"], args, str(result)[:100])
            except Exception as e:
                logger.exception("tool %s execute failed", tc["name"])
                result = f"[工具 {tc['name']} 执行失败: {e}]"
            msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": str(result)})
    logger.warning("tool-loop 达上限 %d 轮,返回最后文本", max_iterations)
    return last_text or "(工具循环达上限,未产出最终回复)"
