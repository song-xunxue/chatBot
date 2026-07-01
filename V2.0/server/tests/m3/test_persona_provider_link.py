"""
persona provider 绑定链路测试(2026-07-02)
stage_persona_inject 把人设 model.provider/model 写入 ctx(非空才覆盖;空=继承全局 chat_provider)。
配套:旧默认人设 provider="glm" 经 init_default_if_absent 迁移为空(兼容旧 seed)。

作者: 李文煜
日期: 2026-07-02
"""
from pipeline.context import MessageContext
from pipeline.stages import stage_persona_inject
from persona.store import get_default_persona, set_persona, init_default_if_absent


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


async def test_init_default_migrates_legacy_glm_provider(fake_redis):
    """兼容:旧版默认人设 provider=glm(旧 ModelBinding 默认)→ init_default_if_absent 迁移为空。
    确保升级后默认人设不会锁死 glm(否则 GLM 限流时切不动)。"""
    card = await get_default_persona(fake_redis)
    card.model.provider = "glm"             # 模拟旧版 seed 的数据
    await set_persona(fake_redis, card)
    await init_default_if_absent(fake_redis)   # 触发一次性迁移
    migrated = await get_default_persona(fake_redis)
    assert migrated.model.provider == ""    # 已迁移为空(=继承全局)
