"""
管道各阶段(stages)
M2 实现:load_history / persona_inject / memory_retrieve / mood_inject / build_messages /
         llm_stream / save / mood_update / memory_write。
适配 V2.0:block 三层 chat_store(get_history(max_messages)/append_message(sender=)) + mood 服务。

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 从 V1.0 移植 stages 到 V2.0;load_history/save 适配 block chat_store 签名;
     新增 stage_mood_inject(before_llm 注入 prompt_hint)/ stage_mood_update(after_llm 情感更新)

2026-06-28
变更说明：
  1. M3 stage_save 把 ai 消息 mid 存入 ctx.reply_mid;新增 stage_score(save 后对 ai 回复
     自动 LLM 评分 + 心情补偿 + 写 score 四元组 + 正负样本归类)
"""
from typing import AsyncIterator
import asyncio
import logging
import time

from redis.asyncio import Redis

from pipeline.context import MessageContext
from llm.base import Message
from llm.registry import get_provider
from storage import chat_store
from core.config import settings

logger = logging.getLogger(__name__)

# 在途后台记忆编码任务强引用集合:防止 asyncio.create_task 的 Task 被 GC 在完成前取消
_BG_TASKS: set[asyncio.Task] = set()


async def stage_load_history(ctx: MessageContext, redis: Redis) -> None:
    """阶段①:从 Redis 取最近对话历史(Working 层),取最近 max_messages 条(block 三层,get_history 只读真实键)"""
    ctx.history = await chat_store.get_history(redis, ctx.object_id,
                                               max_messages=settings.memory_working_window)


async def stage_persona_inject(ctx: MessageContext, redis) -> None:
    """阶段②:人设注入(加载 PersonaCard,渲染 system_prompt)。
    从人设系统按 object_id 解析;缺失则用默认人设。system_prompt 已被上层显式设置时不覆盖。"""
    from persona.store import get_object_persona_id, get_persona, get_default_persona
    from persona.renderer import render_system_prompt
    pid = ctx.persona_id or await get_object_persona_id(redis, ctx.object_id)
    card = await get_persona(redis, pid)
    if card is None:
        card = await get_default_persona(redis)  # 兜底默认人设
    ctx.persona_card = card
    ctx.persona_id = card.id if card else pid
    # 应用人设绑定的 provider/model:仅当 provider 非空才应用(空=继承全局 chat_provider);
    # model 必须跟 provider 一起应用,否则孤立的 model 名(如旧数据 "glm-5.2")会打到别的 provider 报错
    if card and card.model and card.model.provider:
        ctx.provider_name = card.model.provider
        if card.model.model:
            ctx.model = card.model.model
    if not ctx.system_prompt:
        ctx.system_prompt = render_system_prompt(card, card.dynamic_state if card else None)


async def stage_memory_retrieve(ctx: MessageContext, redis) -> None:
    """阶段②.5:记忆检索(插入 persona_inject 与 mood_inject 之间)
    从四级记忆召回相关条目并组装 memory_block,拼入 system_prompt 尾部。
    memory_enabled=False 时跳过(降级无记忆)。"""
    if not settings.memory_enabled:
        return
    from memory.coordinator import get_memory_coordinator
    coord = await get_memory_coordinator()
    result = await coord.retrieve(ctx.object_id, ctx.user_text,
                                  top_k=settings.memory_retrieve_topk,
                                  working_messages=ctx.history)
    ctx.recall_result = result
    ctx.memory_block = coord.render(result)
    ctx.memory_meta = {"hit_mids": result.hit_mids}


async def stage_mood_inject(ctx: MessageContext, redis) -> None:
    """阶段②.6:心情注入(在调 LLM 前)。
    mood.inject_hint 聚合:取 mood + 查档位 + 拼 prompt_hint(格式由 mood own,架构 #5 收口)。
    hint 追加到 system_prompt(影响回复语气),label/kaomoji 写 ctx.plugin_meta 供 QQ 回复/面板展示。"""
    from mood import service
    state = await service.inject_hint(redis, ctx.object_id)
    ctx.mood_value = state["mood"]
    if state["hint"]:
        if ctx.system_prompt:
            ctx.system_prompt += state["hint"]
        ctx.plugin_meta["mood"] = state["label"]
        ctx.plugin_meta["mood_kaomoji"] = state["kaomoji"]


async def stage_build_messages(ctx: MessageContext) -> list[Message]:
    """阶段③:拼装发送给 LLM 的消息列表(system[+memory_block] + 历史 + 本次用户消息)。
    memory_block 拼到 system_prompt 尾部(规避部分 provider 双 system 兼容问题)。"""
    messages: list[Message] = []
    if ctx.system_prompt:
        content = ctx.system_prompt
        if ctx.memory_block:
            content = f"{ctx.system_prompt}\n\n{ctx.memory_block}"
        messages.append(Message(role="system", content=content))
    messages.extend(ctx.history)
    messages.append(Message(role="user", content=ctx.user_text))
    return messages


async def stage_llm_stream(ctx: MessageContext) -> AsyncIterator[str]:
    """阶段④:流式调用 LLM,异步生成器逐 token 产出文本。
    QQ 场景不逐 token 发(由 webhook 累积为完整回复再下发);流式接口保留供 M6 outputpro 分段。"""
    provider = get_provider(ctx.provider_name)
    messages = await stage_build_messages(ctx)
    async for delta in provider.stream_chat(messages, model=ctx.model):
        yield delta.text


async def stage_save(ctx: MessageContext, redis: Redis, *,
                     reply_sender: str = "ai", reply_source: str = "live",
                     user_ts: int | None = None, reply_ts: int | None = None) -> None:
    """阶段④:把本次用户消息 + 回复写入历史(block 三层,落当前 open block)。
    reply_sender/reply_source:pipeline 'ai'/'live';takeover 'proxy'/'proxy'(代答)。
    user_ts/reply_ts:显式 ts(代答同 block 递增保对话连续);None→ctx.created_ts or now / base+1。
    回复 mid 存 ctx.reply_mid,供 stage_score 评分定位。"""
    base_ts = user_ts if user_ts else (ctx.created_ts or int(time.time() * 1000))
    await chat_store.append_message(redis, ctx.object_id,
                                    sender="user", content=ctx.user_text,
                                    source="live", ts=base_ts)
    r_ts = reply_ts if reply_ts else base_ts + 1
    ctx.reply_mid = await chat_store.append_message(redis, ctx.object_id,
                                                    sender=reply_sender, content=ctx.reply_text,
                                                    source=reply_source, ts=r_ts)


async def stage_score(ctx: MessageContext, redis: Redis, *,
                      mood_value: float | None = None,
                      provider_name: str = "") -> dict | None:
    """阶段④.5:对回复自动 LLM 评分(对照人设)+ 心情补偿 + 写 score 四元组 + 样本归类。
    在 stage_save 后执行(用 ctx.reply_mid 定位);score_enabled=False 或无 reply_mid/text 则跳过。
    mood_value/provider_name:pipeline 传 ctx.mood_value/ctx.provider_name;takeover 传 None/""(读 get_mood/默认)。
    软失败(评分异常 → 记日志返回 None,不阻塞)。返回 score 四元组(或 None)。"""
    if not settings.score_enabled:
        return None
    if not ctx.reply_mid or not ctx.reply_text:
        return None
    from score import service as score_service
    try:
        return await score_service.score_reply(
            redis, ctx.object_id, ctx.reply_text, ctx.persona_card, ctx.reply_mid,
            mood_value=mood_value, provider_name=provider_name,
        )
    except Exception:
        logger.exception("score stage failed")   # 评分失败不阻塞主流程与记忆编码
        return None


async def stage_tool_loop(ctx: MessageContext, redis: Redis) -> str | None:
    """阶段③':有注册工具时走 tool-loop(LLM function calling 决策调工具→执行→再推理),
    返回最终回复文本;tool_loop_enable=False 或无注册工具时返回 None(pipeline 降级 stream_chat)。
    对应 docs/01 §6。非流式(QQ 累积完整回复);与 stream 互斥(有工具走 tool-loop,否则 stream)。"""
    if not settings.tool_loop_enable:
        return None
    from tools import get_tool_registry
    from tools.base import ToolContext
    from pipeline.tool_loop import run_tool_loop
    registry = get_tool_registry()
    if not registry.all():
        return None
    provider = get_provider(ctx.provider_name)
    tctx = ToolContext(redis, object_id=ctx.object_id)
    try:
        return await run_tool_loop(provider, ctx.system_prompt, ctx.user_text,
                                   ctx.history, registry, tctx,
                                   model=ctx.model, max_iterations=settings.tool_loop_max_iterations)
    except Exception as e:
        # tool-loop 失败(provider 限流/超时/超上限):降级返回 None → runner 走 stage_llm_stream
        # 兜底保证用户仍收到正常回复(无工具),绝不把错误堆栈当回复发给 QQ 用户
        logger.warning("tool-loop 失败(provider=%s),降级 stream_chat: %s",
                       ctx.provider_name, e)
        return None


async def stage_mood_update(ctx: MessageContext, redis) -> None:
    """阶段④.5:心情情感更新(LLM 产出后)。
    按回复文本关键词情感更新 mood(正向词↑step/负向词↓step)。对应 docs/03 §4.1。
    复用 V1.0 mood_dynamic 行为(用 reply_text);后续可扩展 user_text 共情。"""
    from mood import service
    if ctx.reply_text:
        await service.apply_emotion(redis, ctx.object_id, ctx.reply_text)


async def stage_memory_write(ctx: MessageContext, redis: Redis, *,
                              await_memory: bool = False) -> None:
    """阶段⑤:记忆编码,触发 coordinator.on_turn_complete(Episodic 摘要/反思 + Long-term 事实抽取)。
    memory_enabled=False 跳过。await_memory=False(默认,pipeline):fire-and-forget 后台 task,不阻塞回复 yield;
    True(takeover):同步 await,等编码完再进入下发。软失败(_safe_on_turn 或同步 try 吞,不阻塞)。"""
    if not settings.memory_enabled:
        return
    from memory.coordinator import get_memory_coordinator
    coord = await get_memory_coordinator()
    if await_memory:
        try:
            await coord.on_turn_complete(ctx)
        except Exception:
            logger.exception("memory on_turn_complete failed")
    else:
        task = asyncio.create_task(_safe_on_turn(coord, ctx))
        _BG_TASKS.add(task)                          # 持强引用,防 GC 提前取消
        task.add_done_callback(_BG_TASKS.discard)    # 完成后自动移除,避免集合无限增长


async def _safe_on_turn(coord, ctx) -> None:
    """包装 on_turn_complete,吞掉所有异常避免未捕获告警"""
    try:
        await coord.on_turn_complete(ctx)
    except Exception:
        logger.exception("memory write failed")


async def run_post_reply_chain(ctx: MessageContext, redis: Redis, *,
                                reply_sender: str = "ai", reply_source: str = "live",
                                user_ts: int | None = None, reply_ts: int | None = None,
                                score_mood_value: float | None = None,
                                score_provider: str = "",
                                await_memory: bool = False) -> dict | None:
    """统一回合后副作用链(架构 #1,pipeline 与 takeover 共用):stage_save → stage_score → stage_memory_write。
    消除此前 run_stream 与 resolve_and_deliver 两套手撸编排(save/score/memory 顺序 + 软/硬失败发散、
    append_message ts+1 时序两处手撸)。顺序不变量:score 需 stage_save 写入的 ctx.reply_mid;memory 需 ctx.reply_text。
    save 硬(落库是回合契约);score/memory 软(各自 try 吞,不阻塞)。返回 score 四元组(或 None)。
    mood_update 不在此链——pipeline 在 save 前(后接 ON_MESSAGE_OUT 钩子,可能改 reply_text)、
    takeover 在 memory 后,时序语义不同且与 reply_text 修改耦合,各调用方按既有时机调 stage_mood_update。"""
    await stage_save(ctx, redis, reply_sender=reply_sender, reply_source=reply_source,
                     user_ts=user_ts, reply_ts=reply_ts)
    score = await stage_score(ctx, redis, mood_value=score_mood_value, provider_name=score_provider)
    await stage_memory_write(ctx, redis, await_memory=await_memory)
    return score
