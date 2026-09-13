"""
对话控制存储单测(2026-09-13 静默模式重构版)
覆盖:AI 静默开关 / 手动静默期(set_silence TTL 时间窗+is_silenced+清除)/ msgseq / TTS 配置。
原 FIFO 队列测试已随队列删减移除。

作者: 李文煜
日期: 2026-06-30

2026-09-13
变更说明：
  1. 队列删减:删 queue/pending/resolution 测试;新增静默期测试(TTL 语义用 fakeredis 的 ex 模拟:
     set 带 ex 后 exists=True;fake redis ttl 不推进,过期语义由 ttl>0 断言 + 删除路径覆盖)
"""
import pytest

from storage import takeover_store


# ================ AI 静默开关 ================

async def test_enabled_toggle(fake_redis):
    """set/is_enabled 开关(语义:AI 静默模式)"""
    assert await takeover_store.is_enabled(fake_redis, "u1") is False
    await takeover_store.set_enabled(fake_redis, "u1", True)
    assert await takeover_store.is_enabled(fake_redis, "u1") is True
    await takeover_store.set_enabled(fake_redis, "u1", False)
    assert await takeover_store.is_enabled(fake_redis, "u1") is False


# ================ 手动静默期(自动模式下,手动回复后 AI 暂闭嘴) ================

async def test_silence_window_ttl(fake_redis):
    """set_silence 写 TTL 键(带剩余生存期);is_silenced 命中"""
    assert await takeover_store.is_silenced(fake_redis, "u1") is False
    await takeover_store.set_silence(fake_redis, "u1", 10)
    assert await takeover_store.is_silenced(fake_redis, "u1") is True
    # TTL 已设置(fakeredis 不推进时钟,断言剩余生存期在 (0, 600] 区间)
    ttl = await fake_redis.ttl("mychat:takeover:silence:u1")
    assert 0 < ttl <= 600


async def test_silence_clear(fake_redis):
    """minutes<=0 清除静默窗"""
    await takeover_store.set_silence(fake_redis, "u1", 10)
    await takeover_store.set_silence(fake_redis, "u1", 0)
    assert await takeover_store.is_silenced(fake_redis, "u1") is False


# ================ msgseq(onebot 忽略,保留无害) ================

async def test_next_msg_seq_increments(fake_redis):
    """msg_seq per-oid 递增,不同 oid 独立"""
    assert await takeover_store.next_msg_seq(fake_redis, "u1") == 1
    assert await takeover_store.next_msg_seq(fake_redis, "u1") == 2
    assert await takeover_store.next_msg_seq(fake_redis, "u2") == 1


# ================ 代答 TTS 两开关 ================

async def test_tts_config_roundtrip(fake_redis):
    """get(未设返空 dict)/set(整 JSON 替换)"""
    assert await takeover_store.get_tts_config(fake_redis, "u1") == {}
    await takeover_store.set_tts_config(fake_redis, "u1", True, False)
    assert await takeover_store.get_tts_config(fake_redis, "u1") == \
        {"enable": True, "send_text_also": False}
    await takeover_store.set_tts_config(fake_redis, "u1", False, True)
    assert await takeover_store.get_tts_config(fake_redis, "u1") == \
        {"enable": False, "send_text_also": True}
