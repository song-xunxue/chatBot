"""
roleplay 训练样本 → long_term 记忆抽取编排
把后端录入的 roleplay 训练样本(block 三层,物理隔离)抽成 long_term 记忆事实,
绕过 QQ 对话直接在后端创造记忆(服务于人设反推/记忆召回)。
复用 encoder.extract_facts_batch(防幻觉铁律 + 角色第一人称视角 prompt)。

设计要点(2026-07-07,基于对抗审查):
  1. 过滤 system 旁白:encoder 只分 user/非user,system 会被当"角色(我)"抽事实绕过铁律,
     故编排层过滤 role=='system' 的消息(旁白不是对话,不进抽取)。
  2. 显式构造 Message(roleplay 用 role 字段,非 live 的 sender):绝不能复用 get_history
     的 sender 转换路径(会 KeyError/fallback 把全部当 user,反转防幻觉语义)。
  3. 长 block 分批:encoder 内部 messages[-12:] 截最近 12 条,长 roleplay block 的早期设定
     会被丢,故编排层按每 12 条一组分批抽取,结果合并。
  4. source='roleplay' 标记:抽出的每条 fact 打 source,便于未来审计/批量清理
     (用户选"共池默认进召回",source 仅写入不做读取过滤)。
  5. 不写库:只返回 facts,写由调用方调 coordinator.upsert_facts_batch(持锁批量去重)。

作者: 李文煜
日期: 2026-07-07

2026-07-07
变更说明：
  1. 新建 roleplay→long_term 抽取编排:复用 encoder.extract_facts_batch,
     过滤 system + 显式构造 Message + 分批 + 打 source='roleplay'
"""
import logging

from llm.base import Message

logger = logging.getLogger(__name__)

# 与 encoder.extract_facts_batch 内部 messages[-12:] 对齐:每批最多 12 条控 token
_BATCH_SIZE = 12


async def extract_roleplay_facts(redis, object_id: str, *,
                                  block_id: str | None = None,
                                  llm=None, model: str = "",
                                  user_alias: str = "") -> list[dict]:
    """从 roleplay 训练样本抽 long_term 事实(复用 encoder.extract_facts_batch)。

    取指定会话(block_id 缺省取全部)的 roleplay 消息,过滤 system 旁白 + 显式构造
    Message + 每 _BATCH_SIZE 条分批调 encoder.extract_facts_batch,合并结果并给每条
    打 source='roleplay'。无 LLM/无消息/失败返回空 list(不抛)。

    Args:
        redis: Redis 客户端
        object_id: 会话 object_id
        block_id: 指定 roleplay 会话 block_id;None 取全部会话
        llm: 编码用 LLMProvider;None 时 lazy 解析 resolve_provider('memory')
        model: 编码用模型名;空串用 settings.memory_summary_model

    Returns:
        [{content, importance, emotion, category, source='roleplay'}, ...];无则 []
    """
    from memory import encoder
    from storage import chat_store

    # lazy 解析 provider/model(与 coordinator 一致用 memory provider)
    if llm is None:
        from llm.resolver import resolve_provider
        llm = resolve_provider("memory")
    if not model:
        from core.config import settings
        model = settings.memory_summary_model or ""

    # 取 roleplay 消息(dict 列表,含 role/content;物理隔离键,绝不进 get_history)
    items = await chat_store.list_roleplay(redis, object_id, block_id=block_id)
    if not items:
        return []

    # 过滤 system 旁白 + 空 content,显式构造 Message(roleplay 用 role 字段,非 sender)
    msgs = [
        Message(role=d.get("role", "user"), content=(d.get("content") or ""))
        for d in items
        if d.get("role") != "system" and (d.get("content") or "").strip()
    ]
    if not msgs:
        return []

    # 分批抽取(每 _BATCH_SIZE 条一组,对齐 encoder 内部 messages[-12:] 避免截断丢设定)
    facts: list[dict] = []
    for i in range(0, len(msgs), _BATCH_SIZE):
        batch = msgs[i:i + _BATCH_SIZE]
        got = await encoder.extract_facts_batch(batch, llm, model, user_alias=user_alias)
        if got:
            facts.extend(got)

    # 给每条打 source='roleplay'(便于审计/批量清理;不做读取过滤,尊重"共池默认进召回")
    for f in facts:
        f["source"] = "roleplay"

    logger.info("roleplay 抽取 oid=%s block=%s msgs=%d facts=%d",
                object_id, block_id or "ALL", len(msgs), len(facts))
    return facts
