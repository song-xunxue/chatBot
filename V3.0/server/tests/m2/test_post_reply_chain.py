"""
run_post_reply_chain 单测(架构 #1 统一回合副作用链):
验证 save→score→memory 顺序 + ai(普通回复)/ proxy(代答)两种 sender 共用同一链。

作者: 李文煜
日期: 2026-07-04
"""
from pipeline.context import MessageContext
from pipeline.stages import run_post_reply_chain


async def test_chain_save_ai_and_proxy_shared(fake_redis, monkeypatch):
    """同一链支持 ai(普通回复)与 proxy(代答)两种 sender——架构 #1 收口的核心契约。
    关 score/memory 隔离 save 行为:user+reply 落库 + reply_mid 写 ctx。"""
    from pipeline import stages
    monkeypatch.setattr(stages.settings, "score_enabled", False)
    monkeypatch.setattr(stages.settings, "memory_enabled", False)
    from storage import chat_store

    # ai 普通回复(pipeline 路径:sender=ai, source=live, ts 自动)
    ctx_a = MessageContext(object_id="u1", user_text="hi", reply_text="hello~")
    score_a = await run_post_reply_chain(ctx_a, fake_redis,
                                          reply_sender="ai", reply_source="live",
                                          score_mood_value=ctx_a.mood_value,
                                          score_provider=ctx_a.provider_name, await_memory=False)
    # proxy 代答(takeover 路径:sender=proxy, source=proxy, 显式 ts 同 block 递增, memory sync)
    ctx_p = MessageContext(object_id="u2", user_text="在吗", reply_text="在的~")
    score_p = await run_post_reply_chain(ctx_p, fake_redis,
                                          reply_sender="proxy", reply_source="proxy",
                                          user_ts=1000, reply_ts=1001,
                                          score_mood_value=None, score_provider="",
                                          await_memory=True)

    msg1 = await chat_store.list_messages(fake_redis, "u1")
    msg2 = await chat_store.list_messages(fake_redis, "u2")
    assert [m["sender"] for m in msg1] == ["user", "ai"]      # 普通回复
    assert [m["sender"] for m in msg2] == ["user", "proxy"]   # 代答
    assert msg2[1]["source"] == "proxy"
    assert int(msg2[1]["ts"]) == 1001                          # 显式 reply_ts 生效
    assert ctx_a.reply_mid and ctx_p.reply_mid                 # stage_save 写入 reply_mid
    assert score_a is None and score_p is None                 # score 关闭 → 链返 None


async def test_chain_proxy_ts_continuity(fake_redis, monkeypatch):
    """代答显式 ts:user=base_ts, proxy=base_ts+1(同 block 递增,保对话连续)"""
    from pipeline import stages
    monkeypatch.setattr(stages.settings, "score_enabled", False)
    monkeypatch.setattr(stages.settings, "memory_enabled", False)
    from storage import chat_store
    ctx = MessageContext(object_id="u1", user_text="x", reply_text="y")
    await run_post_reply_chain(ctx, fake_redis, reply_sender="proxy", reply_source="proxy",
                                user_ts=5000, reply_ts=5001,
                                score_mood_value=None, await_memory=True)
    msgs = await chat_store.list_messages(fake_redis, "u1")
    assert int(msgs[0]["ts"]) == 5000 and int(msgs[1]["ts"]) == 5001
