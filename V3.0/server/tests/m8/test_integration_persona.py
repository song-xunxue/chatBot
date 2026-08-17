"""
拟人化集成测试(2026-07-07):端到端验证 user_alias 自动学 + roleplay→long_term 抽取用别名。
跨函数链路(chat_store→coordinator→persona_store / rest 端点→roleplay_extract→encoder),非单函数 mock。

作者: 李文煜
日期: 2026-07-07
"""
from types import SimpleNamespace

import httpx
from fastapi import FastAPI

import storage.redis_client as redis_client
import memory.coordinator as coord_mod
from api.rest_roleplay import router as roleplay_router
from core.config import settings
from persona.models import PersonaCard
from persona import store as persona_store
from storage import chat_store
from memory.coordinator import MemoryCoordinator
from memory import store as mem_store


async def _seed_persona(fake_redis, oid="u1", pid="ptest", **fields):
    """seed 人设 + 绑定 oid,返回 card"""
    card = PersonaCard(id=pid, name="测试角色", **fields)
    await persona_store.set_persona(fake_redis, card)
    await persona_store.bind_object_persona(fake_redis, oid, pid)
    return card


async def test_on_turn_complete_learns_alias_e2e(fake_redis):
    """端到端:用户消息自报称呼 → on_turn_complete 自动学 → persona.user_alias 更新。
    链路:chat_store.append_message(写)→store.get_working_span(读 chat_history)→
    user_alias 正则→persona_store.set_persona(更新)。"""
    card = await _seed_persona(fake_redis)   # user_alias 空
    await chat_store.append_message(fake_redis, "u1", sender="user", content="你可以叫我煜君")
    # llm=None 使 extract/summarize 返回空;1 条消息 turn_count=0,episodic/extract 不触发,只跑自动学
    ctx = SimpleNamespace(object_id="u1", persona_card=card, created_ts=0, last_score=-1.0)
    coord = MemoryCoordinator(fake_redis, llm_provider=None)
    await coord.on_turn_complete(ctx)
    updated = await persona_store.get_persona(fake_redis, "ptest")
    assert updated.user_alias == "煜君"


async def test_on_turn_complete_no_alias_no_change(fake_redis):
    """用户消息无自报称呼 → user_alias 不变(保持空,无误学)"""
    card = await _seed_persona(fake_redis)
    await chat_store.append_message(fake_redis, "u1", sender="user", content="今天天气真好")
    ctx = SimpleNamespace(object_id="u1", persona_card=card, created_ts=0, last_score=-1.0)
    coord = MemoryCoordinator(fake_redis, llm_provider=None)
    await coord.on_turn_complete(ctx)
    updated = await persona_store.get_persona(fake_redis, "ptest")
    assert updated.user_alias == ""


async def test_extract_endpoint_uses_alias_e2e(fake_redis, make_provider, monkeypatch):
    """端到端:roleplay 抽取时 user_alias 传入 encoder prompt(记忆用拟人称呼)。
    链路:seed persona(user_alias=煜君)→录 roleplay→POST extract 端点→
    roleplay_extract 取 persona.user_alias→extract_facts_batch(label=煜君)→mock LLM 收到 prompt 含'煜君'。
    验证:prompt 含'煜君' + long_term 写入 source=roleplay。"""
    await _seed_persona(fake_redis, user_alias="煜君")
    mock_llm = make_provider(
        '[{"content":"煜君喜欢动漫","importance":0.8,"emotion":0.5,"category":"preference"}]')
    coord = MemoryCoordinator(fake_redis, llm_provider=mock_llm)

    async def _get_coord():
        return coord
    monkeypatch.setattr(coord_mod, "get_memory_coordinator", _get_coord)
    monkeypatch.setattr(redis_client, "_redis", fake_redis)
    monkeypatch.setattr(settings, "access_token", "t-token")

    app = FastAPI()
    app.include_router(roleplay_router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as ac:
        await ac.post("/api/v1/roleplay/u1/messages",
                      json={"role": "user", "content": "我喜欢动漫"},
                      headers={"X-Access-Token": "t-token"})
        r = await ac.post("/api/v1/roleplay/u1/extract", json={},
                          headers={"X-Access-Token": "t-token"})
        assert r.status_code == 200
        assert r.json()["written"] == 1
    # 验证 mock LLM 收到的 prompt 含"煜君"(user_alias 传到了 encoder prompt)
    prompt_text = mock_llm.last_messages[0].content
    assert "煜君" in prompt_text
    # 验证 long_term 写入 + source=roleplay
    items = await mem_store.get_all_long_term(fake_redis, "u1")
    assert any("动漫" in m.content and m.source == "roleplay" for m in items)
