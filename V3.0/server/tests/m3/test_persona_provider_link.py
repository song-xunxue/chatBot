"""
persona provider 绑定链路测试(2026-07-02,#6 更新)
stage_persona_inject 把人设 model.provider/model 写入 ctx(非空才覆盖;空=继承全局 chat_provider)。
#6:写缝隙 rest_persona.bind_model 原子校验(model 必须带 provider)→ 从源头杜绝孤立 model,
故 store 的启动迁移已删(此处不再测迁移,改测写缝隙原子约束)。

作者: 李文煜
日期: 2026-07-02
"""
import pytest
from fastapi import HTTPException

from pipeline.context import MessageContext
from pipeline.stages import stage_persona_inject
from persona.store import get_default_persona, set_persona
from api.rest_persona import bind_model


async def test_persona_provider_applied_when_set(fake_redis):
    """人设绑定 provider=deepseek → ctx.provider_name 被覆盖(下拉真正生效)"""
    card = await get_default_persona(fake_redis)   # seed 默认人设(provider="" 新默认)
    card.model.provider = "deepseek"
    card.model.model = "deepseek-chat"
    await set_persona(fake_redis, card)
    ctx = MessageContext(object_id="u1")   # 初始 provider_name=chat_provider(conftest=glm)
    assert ctx.provider_name == "glm"      # 起始非 deepseek
    await stage_persona_inject(ctx, fake_redis)
    assert ctx.provider_name == "deepseek"   # 人设绑定覆盖
    assert ctx.model == "deepseek-chat"


async def test_persona_provider_inherited_when_empty(fake_redis):
    """人设 provider 空 → ctx.provider_name 继承全局 chat_provider(不覆盖)"""
    card = await get_default_persona(fake_redis)
    card.model.provider = ""                # 显式空=继承全局
    await set_persona(fake_redis, card)
    ctx = MessageContext(object_id="u1")   # post_init → chat_provider(glm)
    await stage_persona_inject(ctx, fake_redis)
    assert ctx.provider_name == "glm"      # 未被空值覆盖,保持全局


# —— #6 写缝隙原子约束(model 必须带 provider)——
# 注:bind_model 内部调 get_redis() 单例,需把 fake 注入单例(m3 conftest 的 fake_redis 不注入)

def _inject(monkeypatch, fake):
    monkeypatch.setattr("storage.redis_client._redis", fake)


async def test_bind_model_rejects_model_without_provider(fake_redis, monkeypatch):
    """设 model 不带 provider → 400(杜绝孤立 model 打到错 provider,上次踩的回归)"""
    _inject(monkeypatch, fake_redis)
    card = await get_default_persona(fake_redis)
    with pytest.raises(HTTPException) as exc:
        await bind_model(card.id, {"model": "glm-5.2"})   # 有 model 无 provider
    assert exc.value.status_code == 400


async def test_bind_model_accepts_provider_with_model(fake_redis, monkeypatch):
    """provider + model 一起设 → OK"""
    _inject(monkeypatch, fake_redis)
    card = await get_default_persona(fake_redis)
    res = await bind_model(card.id, {"provider": "deepseek", "model": "deepseek-chat"})
    assert res["model"]["provider"] == "deepseek"
    assert res["model"]["model"] == "deepseek-chat"


async def test_bind_model_accepts_provider_only(fake_redis, monkeypatch):
    """只设 provider(model 空)→ OK"""
    _inject(monkeypatch, fake_redis)
    card = await get_default_persona(fake_redis)
    res = await bind_model(card.id, {"provider": "deepseek"})
    assert res["model"]["provider"] == "deepseek"
    assert res["model"]["model"] == ""


async def test_bind_model_clearing_provider_with_existing_model_rejected(fake_redis, monkeypatch):
    """已绑 model 时再清空 provider → 400(会留孤立 model)"""
    _inject(monkeypatch, fake_redis)
    card = await get_default_persona(fake_redis)
    await bind_model(card.id, {"provider": "deepseek", "model": "deepseek-chat"})  # 先绑好
    with pytest.raises(HTTPException) as exc:   # 再清 provider → 留孤立 model
        await bind_model(card.id, {"provider": ""})
    assert exc.value.status_code == 400
