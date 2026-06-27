"""
score.reverse_infer 单测:_build_diff(白名单/drift/fill_empty vs overwrite) +
infer_and_merge 两步契约(dry_run 返回 diff+token / apply 凭 token 合并+snapshot+回滚留底) +
降级(无样本/无 provider/无 token/错误 token)+ 白名单过滤越权字段。

作者: 李文煜
日期: 2026-06-28

2026-06-28
变更说明:
  1. M3 创建 reverse_infer 单测(_build_diff 纯函数 + infer_and_merge 两步契约全路径 + 降级)
"""
from persona.models import PersonaCard
from persona import store as persona_store
from storage import chat_store
from mood import service as mood_service
from score import service as score_service
from score.reverse_infer import infer_and_merge, _build_diff
from core.config import settings


# ================ _build_diff 纯函数 ================

def test_build_diff_fill_empty_skips_existing():
    """fill_empty 模式:已有值的字段不覆盖,只填空字段"""
    card = PersonaCard(id="p", personality="已有性格")   # profile.speech_style 默认空(待填充)
    diff = _build_diff(card, {"personality": "新的", "speech_style": "轻柔"}, "fill_empty")
    assert "personality" not in diff       # 已有值不覆盖
    assert diff["speech_style"]["new"] == "轻柔"


def test_build_diff_overwrite_skips_drift():
    """overwrite 模式:新值与旧值字符差异>60% 视为漂移,跳过防人格突变"""
    card = PersonaCard(id="p", personality="温柔善良体贴大方")
    diff = _build_diff(card, {"personality": "完全不同的一段性格描述文字"}, "overwrite")
    assert "personality" not in diff


def test_build_diff_whitelist_filters_identity_fields():
    """白名单:核心身份字段(name/id/avatar 等)永不被改写"""
    card = PersonaCard(id="p", name="原名")
    diff = _build_diff(card, {"name": "新名", "id": "hack", "personality": "温柔"}, "fill_empty")
    assert "name" not in diff and "id" not in diff
    assert "personality" in diff


def test_build_diff_max_fields_cap():
    """单次最多改 reverse_infer_max_fields 个字段"""
    card = PersonaCard(id="p")   # 全空
    extracted = {f: f"值{i}" for i, f in enumerate(
        ["personality", "speech_style", "catchphrase", "age", "gender", "occupation", "appearance"])}
    diff = _build_diff(card, extracted, "fill_empty")
    assert len(diff) <= settings.reverse_infer_max_fields


def test_build_diff_truncates_long_field():
    """单字段超字符上限截断"""
    card = PersonaCard(id="p")
    long_catchphrase = "啊" * 100   # catchphrase 上限 30
    diff = _build_diff(card, {"catchphrase": long_catchphrase}, "fill_empty")
    assert len(diff["catchphrase"]["new"]) == 30


# ================ infer_and_merge 两步契约 ================

async def _setup_persona(fake_redis, oid="u1", pid="ptest"):
    """落一个 personality/speech_style 空的人设并绑定到 oid(供反推填充)"""
    card = PersonaCard(id=pid, name="测试角色", creator_notes="核心指令")
    await persona_store.set_persona(fake_redis, card)
    await persona_store.bind_object_persona(fake_redis, oid, pid)
    return card


async def _add_sample(fake_redis, make_provider, monkeypatch, oid, text, base):
    """用 score_reply 产生一条评分样本(正/负由 base+mood 决定)"""
    monkeypatch.setattr(settings, "glm_api_key", "fake-key")
    sp = make_provider(f'{{"score": {base}, "reason": "r"}}')
    monkeypatch.setattr("score.service.get_provider", lambda n: sp)
    card = await persona_store.get_persona(fake_redis, await persona_store.get_object_persona_id(fake_redis, oid))
    mid = await chat_store.append_message(fake_redis, oid, sender="ai", content=text)
    await score_service.score_reply(fake_redis, oid, text, card, mid, mood_value=0.5)


async def test_infer_dry_run_returns_diff_and_token(fake_redis, make_provider, monkeypatch):
    """dry_run:有正样本 → LLM 提炼 → diff(白名单过滤)+ confirm_token"""
    await mood_service.seed_default_kinds(fake_redis)
    await _setup_persona(fake_redis)
    await _add_sample(fake_redis, make_provider, monkeypatch, "u1", "温柔地回应对方", 95)  # positive

    rp = make_provider('{"personality":"温柔体贴","speech_style":"轻柔慢语","name":"应丢弃"}')
    monkeypatch.setattr("score.reverse_infer.get_provider", lambda n: rp)
    res = await infer_and_merge(fake_redis, "u1", dry_run=True)
    assert "confirm_token" in res
    assert res["diff"]["personality"]["new"] == "温柔体贴"
    assert "speech_style" in res["diff"]
    assert "name" not in res["diff"]            # 越权字段丢弃
    assert res["positive_count"] >= 1


async def test_infer_two_step_apply_merges(fake_redis, make_provider, monkeypatch):
    """两步契约:dry_run 拿 token → apply 凭 token 合并 → 人设字段改写 + snapshot 留底"""
    await mood_service.seed_default_kinds(fake_redis)
    await _setup_persona(fake_redis)
    await _add_sample(fake_redis, make_provider, monkeypatch, "u1", "温柔地回应", 95)

    rp = make_provider('{"personality":"温柔体贴","speech_style":"轻柔慢语"}')
    monkeypatch.setattr("score.reverse_infer.get_provider", lambda n: rp)
    res = await infer_and_merge(fake_redis, "u1", dry_run=True)
    token = res["confirm_token"]

    res2 = await infer_and_merge(fake_redis, "u1", dry_run=False, confirm_token=token)
    assert res2["merged"] is True
    applied = await persona_store.get_persona(fake_redis, "ptest")
    assert applied.personality == "温柔体贴"
    assert applied.profile.speech_style == "轻柔慢语"
    assert applied.name == "测试角色"           # 身份字段未改
    assert len(applied.history) >= 1            # snapshot 留底(可回滚)


async def test_infer_apply_consumes_token(fake_redis, make_provider, monkeypatch):
    """apply 后 token 失效,二次 apply 报 token_expired"""
    await mood_service.seed_default_kinds(fake_redis)
    await _setup_persona(fake_redis)
    await _add_sample(fake_redis, make_provider, monkeypatch, "u1", "温柔回应", 95)
    rp = make_provider('{"personality":"温柔"}')
    monkeypatch.setattr("score.reverse_infer.get_provider", lambda n: rp)
    token = (await infer_and_merge(fake_redis, "u1", dry_run=True))["confirm_token"]
    await infer_and_merge(fake_redis, "u1", dry_run=False, confirm_token=token)
    again = await infer_and_merge(fake_redis, "u1", dry_run=False, confirm_token=token)
    assert again["aborted_reason"] == "token_expired_or_invalid"


async def test_infer_apply_no_token_aborts(fake_redis):
    assert (await infer_and_merge(fake_redis, "u1", dry_run=False, confirm_token=""))["aborted_reason"] == "no_token"
    assert (await infer_and_merge(fake_redis, "u1", dry_run=False, confirm_token="bad"))["aborted_reason"] == "token_expired_or_invalid"


async def test_infer_no_samples_aborts(fake_redis, monkeypatch):
    """无评分样本 → aborted(no_samples),不调 LLM"""
    await mood_service.seed_default_kinds(fake_redis)
    await _setup_persona(fake_redis)
    monkeypatch.setattr(settings, "glm_api_key", "fake-key")
    res = await infer_and_merge(fake_redis, "u1", dry_run=True)
    assert res["aborted_reason"] == "no_samples"


async def test_infer_no_provider_aborts(fake_redis, make_provider, monkeypatch):
    """有样本但无可用 provider(key 空)→ aborted(no_llm_provider)"""
    await mood_service.seed_default_kinds(fake_redis)
    await _setup_persona(fake_redis)
    await _add_sample(fake_redis, make_provider, monkeypatch, "u1", "温柔回应", 95)
    # _no_real_llm 已清空 key;但 _add_sample 内又设回 fake-key,这里再清空
    monkeypatch.setattr(settings, "glm_api_key", "")
    res = await infer_and_merge(fake_redis, "u1", dry_run=True)
    assert res["aborted_reason"] == "no_llm_provider"


async def test_infer_llm_empty_aborts(fake_redis, make_provider, monkeypatch):
    """LLM 返回空 JSON → aborted(llm_empty_or_failed)"""
    await mood_service.seed_default_kinds(fake_redis)
    await _setup_persona(fake_redis)
    await _add_sample(fake_redis, make_provider, monkeypatch, "u1", "温柔回应", 95)
    rp = make_provider("不是JSON")
    monkeypatch.setattr("score.reverse_infer.get_provider", lambda n: rp)
    monkeypatch.setattr(settings, "glm_api_key", "fake-key")
    res = await infer_and_merge(fake_redis, "u1", dry_run=True)
    assert res["aborted_reason"] == "llm_empty_or_failed"


async def test_infer_persona_not_found(fake_redis, monkeypatch):
    """对象未绑人设且 default 缺失 → aborted(persona_not_found)"""
    await mood_service.seed_default_kinds(fake_redis)
    monkeypatch.setattr(settings, "glm_api_key", "fake-key")
    # 不 seed 任何人设,get_object_persona_id 返回 default 但 get_persona(default)=None
    res = await infer_and_merge(fake_redis, "ghost", dry_run=True)
    assert res["aborted_reason"] == "persona_not_found"
