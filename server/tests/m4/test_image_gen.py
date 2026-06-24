"""
image_gen 插件测试：配额内生成图(入 ctx.rich.image)、超额自主拒绝(STOP)、provider 失败回滚配额。
经 real_manager 加载真实 image_gen 插件，fakeredis 计数验证日配额。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M4.3 覆盖 image_gen：配额生成/超额拒绝
  2. M4.3-review 补：provider 失败回滚配额、超额清理富内容
"""
from datetime import date

from plugins.base import ON_AFTER_LLM
from modality import register_image, ImageProvider, ImageArtifact


def _ctx(reply="", oid="o1"):
    return type("C", (), {
        "object_id": oid, "user_text": "", "reply_text": reply,
        "rich": {}, "plugin_meta": {},
    })()


async def test_under_quota_generates_image(real_manager):
    await real_manager.load_all()
    await real_manager.set_global_enabled("image_gen", True)
    ctx = _ctx(reply="看这只猫")
    res = await real_manager._bus.fire(ON_AFTER_LLM, ctx)
    assert res == "continue"
    assert len(ctx.rich.get("image", [])) == 1
    assert ctx.rich["image"][0]["url"].startswith("stub://img/")


async def test_over_quota_refuses(real_manager):
    """日配额默认 5：前 5 次生成，第 6 次超额拒绝"""
    await real_manager.load_all()
    await real_manager.set_global_enabled("image_gen", True)
    for i in range(5):
        await real_manager._bus.fire(ON_AFTER_LLM, _ctx(reply=f"图{i}"))
    c6 = _ctx(reply="再来一张")
    res = await real_manager._bus.fire(ON_AFTER_LLM, c6)
    assert res == "stop"
    assert len(c6.rich.get("image", [])) == 0           # 未生成
    assert c6.plugin_meta.get("image_refused") is True
    assert "歇" in c6.reply_text or "太多" in c6.reply_text


async def test_custom_quota_via_config(real_manager):
    """按对象配置 daily_quota=2：第3次即拒绝"""
    await real_manager.load_all()
    await real_manager.set_global_enabled("image_gen", True)
    await real_manager.set_object_config("image_gen", "o9", True, {"daily_quota": 2})
    for i in range(2):
        await real_manager._bus.fire(ON_AFTER_LLM, _ctx(reply="x", oid="o9"))
    c3 = _ctx(reply="x", oid="o9")
    res = await real_manager._bus.fire(ON_AFTER_LLM, c3)
    assert res == "stop"


async def test_provider_failure_rolls_back_quota(real_manager):
    """provider 生成失败时配额回滚（不泄漏）"""
    class _BoomImg(ImageProvider):
        name = "boom"
        async def generate(self, prompt, size="", **opts):
            raise RuntimeError("provider down")

    register_image("boom", _BoomImg)
    await real_manager.load_all()
    await real_manager.set_global_enabled("image_gen", True)
    await real_manager.set_object_config("image_gen", "o7", True, {"provider": "boom"})
    ctx = _ctx(reply="x", oid="o7")
    await real_manager._bus.fire(ON_AFTER_LLM, ctx)   # 异常被总线隔离
    used = await real_manager._redis.get(f"mychat:quota:o7:img:{date.today().isoformat()}")
    assert (int(used) if used else 0) == 0             # INCR 后失败已 DECR 回滚


async def test_refuse_clears_stale_rich(real_manager):
    """超额拒绝时清理本回合已收集的 audio（防文本/音频错配）"""
    await real_manager.load_all()
    await real_manager.set_global_enabled("image_gen", True)
    await real_manager.set_global_enabled("tts", True)   # tts 先收集 audio
    await real_manager.set_object_config("image_gen", "o8", True, {"daily_quota": 1})
    # 第1次：配额内生成
    await real_manager._bus.fire(ON_AFTER_LLM, _ctx(reply="x", oid="o8"))
    # 第2次：超额拒绝，应清理 audio
    c2 = _ctx(reply="y", oid="o8")
    c2.rich["audio"] = [{"url": "stale"}]                # 模拟 tts 已收集
    res = await real_manager._bus.fire(ON_AFTER_LLM, c2)
    assert res == "stop"
    assert "audio" not in c2.rich                        # 已清理

