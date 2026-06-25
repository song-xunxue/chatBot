"""
对话历史存储 chat_store 测试（基于 fakeredis）
验证 append / get_history / clear_history 的时序、隔离、limit 截断、中文保真

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M2 验证：覆盖 chat_store 全部接口
"""
from storage import chat_store
from llm.base import Message


async def test_append_and_get_history(fake_redis):
    await chat_store.append_message(fake_redis, "u1", "user", "你好")
    await chat_store.append_message(fake_redis, "u1", "assistant", "你好呀")
    hist = await chat_store.get_history(fake_redis, "u1", limit=20)
    assert hist == [
        Message(role="user", content="你好"),
        Message(role="assistant", content="你好呀"),
    ]


async def test_history_isolated_per_object(fake_redis):
    await chat_store.append_message(fake_redis, "a", "user", "A1")
    await chat_store.append_message(fake_redis, "b", "user", "B1")
    assert len(await chat_store.get_history(fake_redis, "a")) == 1
    assert len(await chat_store.get_history(fake_redis, "b")) == 1


async def test_get_history_limit_returns_last_n(fake_redis):
    for i in range(5):
        await chat_store.append_message(fake_redis, "u", "user", f"m{i}")
    hist = await chat_store.get_history(fake_redis, "u", limit=3)
    # 取最后 3 条、时间正序：m2, m3, m4
    assert [m.content for m in hist] == ["m2", "m3", "m4"]


async def test_clear_history(fake_redis):
    await chat_store.append_message(fake_redis, "u", "user", "x")
    await chat_store.clear_history(fake_redis, "u")
    assert await chat_store.get_history(fake_redis, "u") == []


async def test_chinese_and_emoji_preserved(fake_redis):
    # JSON 序列化 ensure_ascii=False，中文/emoji 应原样存取
    await chat_store.append_message(fake_redis, "u", "user", "你好世界🎉")
    hist = await chat_store.get_history(fake_redis, "u")
    assert hist[0].content == "你好世界🎉"
