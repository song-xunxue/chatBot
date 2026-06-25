"""
reply_enhance 插件测试：输出合并、输入累积(暂缓/攒够 flush)。
经 real_manager 加载真实 reply_enhance 插件，按对象配置 accumulate，经总线触发验证。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M4.3 覆盖 reply_enhance：合并/累积/暂缓/flush
"""
from plugins.base import ON_MESSAGE_IN, ON_BEFORE_LLM, ON_MESSAGE_OUT


def _ctx(text="", reply="", oid="o1"):
    return type("C", (), {
        "object_id": oid, "user_text": text, "reply_text": reply,
        "rich": {}, "plugin_meta": {},
    })()


async def test_output_merge_collapses_blank_lines(real_manager):
    await real_manager.load_all()
    await real_manager.set_global_enabled("reply_enhance", True)
    ctx = _ctx(reply="a\n\n\n\nb")
    await real_manager._bus.fire(ON_MESSAGE_OUT, ctx)
    assert ctx.reply_text == "a\n\nb"


async def test_accumulate_holds_then_flushes(real_manager):
    await real_manager.load_all()
    await real_manager.set_global_enabled("reply_enhance", True)
    await real_manager.set_object_config("reply_enhance", "o1", True,
                                         {"accumulate": True, "flush_count": 3, "merge_blank_lines": True})
    bus = real_manager._bus
    # 第1、2条：缓冲未攒够 → held(STOP)
    for t in ("嗯", "然后呢"):
        c = _ctx(text=t)
        await bus.fire(ON_MESSAGE_IN, c)
        await bus.fire(ON_BEFORE_LLM, c)
        assert c.plugin_meta.get("held") is True
    # 第3条：达 flush_count=3 → flush，合并3条，清缓冲
    c3 = _ctx(text="就这样。")
    await bus.fire(ON_MESSAGE_IN, c3)
    await bus.fire(ON_BEFORE_LLM, c3)
    assert c3.plugin_meta.get("held") is not True
    assert "嗯" in c3.user_text and "然后呢" in c3.user_text and "就这样" in c3.user_text


async def test_semantic_complete_flushes_early(real_manager):
    """末条带句末标点 → 即使未达 flush_count 也 flush"""
    await real_manager.load_all()
    await real_manager.set_global_enabled("reply_enhance", True)
    await real_manager.set_object_config("reply_enhance", "o1", True,
                                         {"accumulate": True, "flush_count": 10})
    c = _ctx(text="今天天气真好。")
    await real_manager._bus.fire(ON_MESSAGE_IN, c)
    await real_manager._bus.fire(ON_BEFORE_LLM, c)
    assert c.plugin_meta.get("held") is not True     # 句末标点 → 立即 flush
