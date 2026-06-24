"""
反推人设·直接合并测试（V1.1 M12）
覆盖 _build_diff（白名单/fill_empty/overwrite drift/截断/嵌套/上限）+
infer_and_merge 两步契约（dry_run/apply/no_samples/no_provider/bad_token）。
LLM 用 monkeypatch mock，不调真实 API。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. V1.1 M12 覆盖 reverse_infer 核心逻辑
"""
from persona import reverse_infer as ri
from persona.models import PersonaCard
from persona import store as persona_store
from storage import chat_store


# —— 纯函数 _build_diff ——

def test_build_diff_whitelist_filters_identity():
    card = PersonaCard(id="p", name="N")
    extracted = {"name": "黑客", "id": "x", "avatar": "bad", "personality": "温柔"}
    diff = ri._build_diff(card, extracted, "fill_empty")
    assert "name" not in diff and "id" not in diff and "avatar" not in diff
    assert "personality" in diff


def test_build_diff_fill_empty_skips_existing():
    card = PersonaCard(id="p", personality="原有")
    extracted = {"personality": "新值", "catchphrase": "喵"}
    diff = ri._build_diff(card, extracted, "fill_empty")
    assert "personality" not in diff          # 已有值→跳过
    assert diff["catchphrase"]["new"] == "喵"


def test_build_diff_overwrite_rejects_drift():
    card = PersonaCard(id="p", personality="温柔善良可爱")
    extracted = {"personality": "1234567890完全不同xyz"}   # drift > 0.6
    diff = ri._build_diff(card, extracted, "overwrite")
    assert "personality" not in diff


def test_build_diff_truncation():
    card = PersonaCard(id="p")
    extracted = {"catchphrase": "啊" * 100}   # 超 MAX_FIELD_CHARS[catchphrase]=30
    diff = ri._build_diff(card, extracted, "fill_empty")
    assert len(diff["catchphrase"]["new"]) == 30


def test_build_diff_nested_profile():
    card = PersonaCard(id="p")
    extracted = {"age": "16岁", "gender": "女", "likes": ["猫", "甜食"]}
    diff = ri._build_diff(card, extracted, "fill_empty")
    assert diff["age"]["new"] == "16岁"
    assert diff["gender"]["new"] == "女"
    assert diff["likes"]["new"] == ["猫", "甜食"]


def test_build_diff_max_fields_cap():
    card = PersonaCard(id="p")
    extracted = {f: f"v{f}" for f in ri.FIELD_WHITELIST}
    diff = ri._build_diff(card, extracted, "fill_empty")
    assert len(diff) <= ri.MAX_FIELDS_TOUCHED


# —— infer_and_merge（fake_redis + monkeypatch mock LLM）——

async def test_infer_no_positive_samples(fake_redis):
    await persona_store.set_persona(fake_redis, PersonaCard(id="p", name="N"))
    await persona_store.bind_object_persona(fake_redis, "o1", "p")
    r = await ri.infer_and_merge(fake_redis, "o1", dry_run=True)
    assert r["aborted_reason"] == "no_positive_samples"


async def test_infer_no_provider(monkeypatch, fake_redis):
    await persona_store.set_persona(fake_redis, PersonaCard(id="p", name="N"))
    await persona_store.bind_object_persona(fake_redis, "o1", "p")
    await chat_store.append_roleplay_pair(fake_redis, "o1", "你好", "嗨~")
    monkeypatch.setattr(ri, "available_providers", lambda: [])
    r = await ri.infer_and_merge(fake_redis, "o1", dry_run=True)
    assert r["aborted_reason"] == "no_llm_provider"


async def test_infer_dry_run_returns_token_no_write(monkeypatch, fake_redis):
    await persona_store.set_persona(fake_redis, PersonaCard(id="p", name="N"))
    await persona_store.bind_object_persona(fake_redis, "o1", "p")
    await chat_store.append_roleplay_pair(fake_redis, "o1", "你好", "嗨~")
    monkeypatch.setattr(ri, "available_providers", lambda: ["glm"])

    async def fake_extract(pos, neg, llm):
        return {"personality": "温柔", "catchphrase": "喵"}

    monkeypatch.setattr(ri, "_llm_extract", fake_extract)
    r = await ri.infer_and_merge(fake_redis, "o1", dry_run=True)
    assert "confirm_token" in r and r["diff"]
    assert r["diff"]["personality"]["new"] == "温柔"
    # dry_run 不落库
    card = await persona_store.get_persona(fake_redis, "p")
    assert card.personality == ""


async def test_infer_apply_merges_and_snapshots(monkeypatch, fake_redis):
    await persona_store.set_persona(fake_redis, PersonaCard(id="p", name="N"))
    await persona_store.bind_object_persona(fake_redis, "o1", "p")
    await chat_store.append_roleplay_pair(fake_redis, "o1", "你好", "嗨~")
    monkeypatch.setattr(ri, "available_providers", lambda: ["glm"])

    async def fake_extract(pos, neg, llm):
        return {"catchphrase": "喵"}

    monkeypatch.setattr(ri, "_llm_extract", fake_extract)
    r = await ri.infer_and_merge(fake_redis, "o1", dry_run=True)
    token = r["confirm_token"]
    r2 = await ri.infer_and_merge(fake_redis, "o1", dry_run=False, confirm_token=token)
    assert r2["merged"] is True
    card = await persona_store.get_persona(fake_redis, "p")
    assert card.profile.catchphrase == "喵"
    assert len(card.history) >= 1           # snapshot 留底


async def test_infer_apply_bad_token(fake_redis):
    await persona_store.set_persona(fake_redis, PersonaCard(id="p", name="N"))
    r = await ri.infer_and_merge(fake_redis, "o1", dry_run=False, confirm_token="bad")
    assert r["aborted_reason"] == "token_expired_or_invalid"


async def test_infer_apply_no_token(fake_redis):
    await persona_store.set_persona(fake_redis, PersonaCard(id="p", name="N"))
    r = await ri.infer_and_merge(fake_redis, "o1", dry_run=False, confirm_token="")
    assert r["aborted_reason"] == "no_token"
