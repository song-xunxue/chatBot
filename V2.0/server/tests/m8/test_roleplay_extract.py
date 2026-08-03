"""
roleplay 训练样本 → long_term 记忆抽取单测(2026-07-07):
- extract_roleplay_facts 编排:system 过滤 + 空 content 过滤 + Message 构造 + 分批 + source='roleplay'
- coordinator.upsert_facts_batch:批量写入 + 同批去重 + 返回统计 + 不升级 core + source 默认 dialog
- POST /roleplay/{oid}/extract 端点:手动触发写入 long_term
- score _collect_sample/record_score_sample:source 标记(dialog/roleplay,修已存在共池污染)

作者: 李文煜
日期: 2026-07-07
"""
import httpx
from fastapi import FastAPI

import storage.redis_client as redis_client
import memory.coordinator as coord_mod
from api.rest_roleplay import router as roleplay_router
from core.config import settings
from storage import chat_store
from memory import store as mem_store
from memory.coordinator import MemoryCoordinator
from memory.roleplay_extract import extract_roleplay_facts


# ================ extract_roleplay_facts 编排纯逻辑 ================

async def test_extract_filters_system_and_empty(fake_redis, make_provider):
    """system 旁白 + 空 content 被过滤,不进抽取(防 encoder 把 system 当"角色(我)"绕过铁律)"""
    await chat_store.append_roleplay_message(fake_redis, "u1", role="user", content="我喜欢动漫")
    await chat_store.append_roleplay_message(fake_redis, "u1", role="assistant", content="好啊")
    await chat_store.append_roleplay_message(fake_redis, "u1", role="system", content="场景:黄昏的教室")
    await chat_store.append_roleplay_message(fake_redis, "u1", role="user", content="")  # 空,过滤
    llm = make_provider(
        '[{"content":"用户喜欢动漫","importance":0.8,"emotion":0.5,"category":"preference"}]')
    facts = await extract_roleplay_facts(fake_redis, "u1", llm=llm, model="m")
    assert len(facts) == 1
    assert facts[0]["content"] == "用户喜欢动漫"
    assert facts[0]["source"] == "roleplay"   # 打 source 标记
    # 验证喂给 LLM 的 prompt 不含 system 旁白 / 空 content(只有 user/assistant 配对)
    prompt_text = llm.last_messages[0].content
    assert "场景:黄昏的教室" not in prompt_text
    assert "我喜欢动漫" in prompt_text


async def test_extract_no_messages_returns_empty(fake_redis, make_provider):
    """无 roleplay 消息 → 返回空 list(不调 LLM)"""
    llm = make_provider('[]')
    facts = await extract_roleplay_facts(fake_redis, "u1", llm=llm, model="m")
    assert facts == []
    assert llm.call_count == 0


async def test_extract_no_llm_returns_empty(fake_redis):
    """无 LLM provider → extract_facts_batch 返回空,编排返回空 list(不抛)"""
    await chat_store.append_roleplay_message(fake_redis, "u1", role="user", content="hi")
    facts = await extract_roleplay_facts(fake_redis, "u1", llm=None, model="m")
    assert facts == []


async def test_extract_batches_long_block(fake_redis, make_provider):
    """长 block(>12 条)分批抽取:每 12 条一组,多批结果合并(对齐 encoder messages[-12:])"""
    for i in range(25):
        await chat_store.append_roleplay_message(fake_redis, "u1", role="user", content=f"内容{i}")
    llm = make_provider('[{"content":"事实","importance":0.5,"emotion":0,"category":"fact"}]')
    facts = await extract_roleplay_facts(fake_redis, "u1", llm=llm, model="m")
    # 25 条 / 12 = 3 批(12+12+1),每批调一次 LLM 返回 1 条 → 3 条
    assert llm.call_count == 3
    assert len(facts) == 3
    assert all(f["source"] == "roleplay" for f in facts)


async def test_extract_block_id_filter(fake_redis, make_provider):
    """block_id 指定只抽该会话(不混其他会话消息)"""
    b1 = await chat_store.new_roleplay_block(fake_redis, "u1")
    bid1 = b1["block_id"]
    await chat_store.append_roleplay_message(fake_redis, "u1", role="user", content="会话1内容")
    # 开新会话录另一条
    await chat_store.new_roleplay_block(fake_redis, "u1")
    await chat_store.append_roleplay_message(fake_redis, "u1", role="user", content="会话2内容")
    llm = make_provider('[{"content":"事实","importance":0.5,"emotion":0,"category":"fact"}]')
    await extract_roleplay_facts(fake_redis, "u1", block_id=bid1, llm=llm, model="m")
    # 只抽 block1 → prompt 只含"会话1内容"
    prompt_text = llm.last_messages[0].content
    assert "会话1内容" in prompt_text
    assert "会话2内容" not in prompt_text


# ================ coordinator.upsert_facts_batch ================

async def test_upsert_facts_batch_writes_and_dedups(fake_redis):
    """批量写入:新增 + 同批语义去重(无 embedding 降级 Jaccard),统计 written/skipped_dup"""
    coord = MemoryCoordinator(fake_redis, llm_provider=None)
    facts = [
        {"content": "用户喜欢动漫", "importance": 0.8, "emotion": 0.5,
         "category": "preference", "source": "roleplay"},
        {"content": "用户喜欢动漫", "importance": 0.7, "emotion": 0.4,
         "category": "preference", "source": "roleplay"},   # 与上条 Jaccard 去重
    ]
    res = await coord.upsert_facts_batch("u1", facts)
    assert res["written"] == 1
    assert res["skipped_dup"] == 1
    assert len(res["written_mids"]) == 1
    items = await mem_store.get_all_long_term(fake_redis, "u1")
    assert len(items) == 1
    assert items[0].source == "roleplay"   # source 从 fact 读取(不再硬编码 dialog)


async def test_upsert_facts_batch_source_defaults_dialog(fake_redis):
    """fact 未带 source → 默认 dialog(向后兼容 live 路径)"""
    coord = MemoryCoordinator(fake_redis, llm_provider=None)
    await coord.upsert_facts_batch("u1", [
        {"content": "普通事实", "importance": 0.5, "emotion": 0, "category": "fact"}])
    items = await mem_store.get_all_long_term(fake_redis, "u1")
    assert items[0].source == "dialog"


async def test_upsert_facts_batch_empty_noop(fake_redis):
    """空 facts → 全 0,不报错"""
    coord = MemoryCoordinator(fake_redis, llm_provider=None)
    res = await coord.upsert_facts_batch("u1", [])
    assert res["written"] == 0 and res["skipped_dup"] == 0
    assert res["written_mids"] == []


async def test_upsert_facts_batch_no_core_upgrade(fake_redis):
    """roleplay fact 走 upsert_facts_batch 不升级 core(走公开入口不调 _upsert_core_fact)。
    即便 importance>=0.8 + category=relationship 也不进 core,天然防常驻污染。"""
    coord = MemoryCoordinator(fake_redis, llm_provider=None)
    facts = [{"content": "我和用户是恋人", "importance": 0.95, "emotion": 0.9,
              "category": "relationship", "source": "roleplay"}]
    await coord.upsert_facts_batch("u1", facts)
    core = await mem_store.get_core(fake_redis, "u1")
    assert len(core) == 0


# ================ score source 标记(2026-07-07 修已存在共池污染)================

async def test_collect_sample_default_source_dialog(fake_redis):
    """live 评分样本 _collect_sample 默认 source='dialog'"""
    from score import service as score_service
    await score_service._collect_sample(fake_redis, "u1", "positive", "m1", "真实对话回复", 95)
    samples = await score_service.list_samples(fake_redis, "u1", "positive")
    assert samples[0]["source"] == "dialog"


async def test_record_score_sample_default_source_roleplay(fake_redis):
    """roleplay 评分联动 record_score_sample 默认 source='roleplay'(供 roleplay 路径)"""
    from score import service as score_service
    await score_service.record_score_sample(fake_redis, "u1", "m1", "剧本回复", 95)
    samples = await score_service.list_samples(fake_redis, "u1", "positive")
    assert samples[0]["source"] == "roleplay"


# ================ POST /roleplay/{oid}/extract 端点集成 ================

_H = {"X-Access-Token": "t-token"}


def _wire(monkeypatch, fake):
    monkeypatch.setattr(redis_client, "_redis", fake)
    monkeypatch.setattr(settings, "access_token", "t-token")
    app = FastAPI()
    app.include_router(roleplay_router)
    return app


async def _aclient(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_extract_endpoint_writes_memory(monkeypatch, fake_redis, make_provider):
    """POST /roleplay/{oid}/extract:roleplay 训练样本 → long_term 端到端"""
    app = _wire(monkeypatch, fake_redis)
    mock_llm = make_provider(
        '[{"content":"用户喜欢动漫","importance":0.8,"emotion":0.5,"category":"preference"}]')
    coord = MemoryCoordinator(fake_redis, llm_provider=mock_llm)

    async def _mock_get_coord():
        return coord
    monkeypatch.setattr(coord_mod, "get_memory_coordinator", _mock_get_coord)

    async with await _aclient(app) as ac:
        await ac.post("/api/v1/roleplay/u1/messages",
                      json={"role": "user", "content": "我喜欢动漫"}, headers=_H)
        r = await ac.post("/api/v1/roleplay/u1/extract", json={}, headers=_H)
        assert r.status_code == 200
        body = r.json()
        assert body["extracted"] == 1
        assert body["written"] == 1
        assert len(body["written_mids"]) == 1
    # 落库验证 long_term 有 source='roleplay' 条目
    items = await mem_store.get_all_long_term(fake_redis, "u1")
    assert any(m.source == "roleplay" and "动漫" in m.content for m in items)


async def test_extract_endpoint_auth_required(monkeypatch, fake_redis):
    """无 token → 401"""
    app = _wire(monkeypatch, fake_redis)
    async with await _aclient(app) as ac:
        r = await ac.post("/api/v1/roleplay/u1/extract", json={})
        assert r.status_code == 401
