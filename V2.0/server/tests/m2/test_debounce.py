"""
连发防抖单测:用户连发 N 条 → 合并为 1 次 LLM 调用 + 1 次被动回复。
对应 docs/02 §7(连发合并)。

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 创建连发防抖单测
"""
import asyncio

import storage.redis_client as redis_client
from qq import webhook
from qq.types import C2CMessage
from mood import service


async def test_debounce_merges_burst(fake_redis, mock_provider, monkeypatch):
    """连发 3 条合并为 1 次 LLM 调用 + 1 次被动回复,内容含全部连发"""
    monkeypatch.setattr(redis_client, "_redis", fake_redis)
    await service.seed_default_kinds(fake_redis)
    monkeypatch.setattr("pipeline.stages.get_provider", lambda name: mock_provider)
    # 缩短防抖窗口加速测试
    monkeypatch.setattr(webhook.settings, "input_debounce_sec", 0.05)
    # mock 发消息,避免真调 QQ REST
    sent = []

    async def fake_send(openid, content, *, msg_id="", msg_seq=1):
        sent.append((openid, content, msg_id))

    monkeypatch.setattr(webhook, "send_c2c_message", fake_send)

    # 连发 3 条(模拟用户快速连发)
    for i in range(3):
        msg = C2CMessage(openid="u1", content=f"msg{i}", msg_id=f"mid{i}", timestamp="", raw={})
        await webhook._schedule_debounce(msg)
        await asyncio.sleep(0.01)   # 错开一点,确保都进缓冲

    # 等防抖超时 + pipeline 执行
    await asyncio.sleep(0.3)

    assert mock_provider.call_count == 1           # 合并为 1 次 LLM
    assert len(sent) == 1                          # 1 次被动回复
    # 验证连发合并:LLM 收到的单条 user 消息含全部连发内容(合并进 ctx.user_text)
    user_msgs = [m for m in mock_provider.last_messages if m.role == "user"]
    assert len(user_msgs) == 1
    assert "msg0" in user_msgs[0].content and "msg2" in user_msgs[0].content
    assert sent[0][2] == "mid2"                    # 用最新 msg_id 被动回复


async def test_debounce_separate_users_independent(fake_redis, mock_provider, monkeypatch):
    """不同用户的连发各自独立防抖(各自 1 次 LLM)"""
    monkeypatch.setattr(redis_client, "_redis", fake_redis)
    await service.seed_default_kinds(fake_redis)
    monkeypatch.setattr("pipeline.stages.get_provider", lambda name: mock_provider)
    monkeypatch.setattr(webhook.settings, "input_debounce_sec", 0.05)

    async def fake_send(openid, content, *, msg_id="", msg_seq=1):
        pass

    monkeypatch.setattr(webhook, "send_c2c_message", fake_send)

    for oid in ("u1", "u2"):
        msg = C2CMessage(openid=oid, content="hi", msg_id=f"m_{oid}", timestamp="", raw={})
        await webhook._schedule_debounce(msg)

    await asyncio.sleep(0.3)
    assert mock_provider.call_count == 2           # 两个用户各 1 次
