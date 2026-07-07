"""
continuous_send 插件单测(2026-07-07):
1. split_reply 纯函数(单行/多行/超 max 合并尾部/空行过滤)
2. on_message_out 分段发 + msg_seq 递增(QQ 同 msg_id 必须不同 msg_seq)+ reply_sent 标记 + 不改 reply_text
3. on_before_llm 思考延迟(LLM 前随机等待)

作者: 李文煜
日期: 2026-07-07
"""
import asyncio

from plugins.continuous_send.plugin import split_reply, ContinuousSendPlugin
from plugins.base import PluginContext
from plugins.manifest import PluginManifest
from pipeline.context import MessageContext


class _FakeManager:
    """轻量 mock:get_params 返空(插件用代码默认值)"""
    async def get_params(self, name, oid):
        return {}


def _make_plugin():
    p = ContinuousSendPlugin()
    p.manifest = PluginManifest(name="continuous_send")
    p.pctx = PluginContext(manager=_FakeManager(), redis=None, settings=None, manifest=p.manifest)
    return p


# ================ split_reply 纯函数 ================

def test_split_reply_single_line_no_split():
    """单行 < min_segments(2) → 不拆返空(交单条发)"""
    assert split_reply("就一句", 3, 2) == []


def test_split_reply_three_lines_user_example():
    """用户例子:3 行 → 3 段"""
    text = "嗯？\n夫君这么晚还在撒娇呀\n是不是又熬夜了"
    assert split_reply(text, 3, 2) == ["嗯？", "夫君这么晚还在撒娇呀", "是不是又熬夜了"]


def test_split_reply_filters_blank_lines():
    """空行/纯空白行过滤掉"""
    assert split_reply("甲\n\n乙\n  \n丙", 3, 2) == ["甲", "乙", "丙"]


def test_split_reply_over_max_merges_tail():
    """超 max_segments:前 max-1 段独立,尾部合并到第 max 段(内容不丢)"""
    out = split_reply("a\nb\nc\nd\ne", 3, 2)
    assert len(out) == 3
    assert out[0] == "a" and out[1] == "b"
    assert "c" in out[2] and "d" in out[2] and "e" in out[2]


def test_split_reply_empty_text():
    """空文本 → 空"""
    assert split_reply("", 3, 2) == []


# ================ on_message_out 分段(msg_seq 递增)================

async def test_on_message_out_splits_with_incrementing_msg_seq(monkeypatch):
    """3 行 → 逐段发 3 次 + msg_seq 递增[1,2,3](QQ 同 msg_id 必须不同 msg_seq)+ reply_sent=True + reply_text 完整"""
    sent = []

    async def _fake_send(openid, content, msg_id="", msg_seq=1, human_authored=False):
        sent.append({"openid": openid, "content": content, "msg_id": msg_id, "msg_seq": msg_seq})

    import qq.api_client as qq_api
    monkeypatch.setattr(qq_api, "send_c2c_message", _fake_send)
    p = _make_plugin()
    ctx = MessageContext(object_id="u1",
                         reply_text="嗯？\n夫君这么晚还在撒娇呀\n是不是又熬夜了")
    ctx.qq_msg_id = "msgX"
    await p.on_message_out(ctx)
    assert len(sent) == 3
    assert [s["content"] for s in sent] == ["嗯？", "夫君这么晚还在撒娇呀", "是不是又熬夜了"]
    assert [s["msg_seq"] for s in sent] == [1, 2, 3]   # 关键:msg_seq 递增,否则 QQ 拒第 2 段
    assert all(s["msg_id"] == "msgX" for s in sent)
    assert ctx.reply_sent is True
    assert "\n" in ctx.reply_text   # reply_text 未改(save 存完整)


async def test_on_message_out_single_line_no_send(monkeypatch):
    """单行回复不拆 → 不调 send"""
    sent = []

    async def _fake_send(openid, content, msg_id="", msg_seq=1, human_authored=False):
        sent.append(content)

    import qq.api_client as qq_api
    monkeypatch.setattr(qq_api, "send_c2c_message", _fake_send)
    p = _make_plugin()
    ctx = MessageContext(object_id="u1", reply_text="就一句")
    ctx.qq_msg_id = "msgX"
    await p.on_message_out(ctx)
    assert sent == []
    assert ctx.reply_sent is False


async def test_on_message_out_no_msg_id_skip(monkeypatch):
    """无 qq_msg_id(代答主动发等场景)→ 不处理"""
    sent = []

    async def _fake_send(openid, content, msg_id="", msg_seq=1, human_authored=False):
        sent.append(content)

    import qq.api_client as qq_api
    monkeypatch.setattr(qq_api, "send_c2c_message", _fake_send)
    p = _make_plugin()
    ctx = MessageContext(object_id="u1", reply_text="甲\n乙\n丙")
    await p.on_message_out(ctx)
    assert sent == []


# ================ on_before_llm 思考延迟 ================

async def test_on_before_llm_sleeps_random_delay(monkeypatch):
    """on_before_llm:LLM 前 sleep 随机思考延迟(默认 3-5s)"""
    slept = []

    async def _fake_sleep(d):
        slept.append(d)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
    p = _make_plugin()
    ctx = MessageContext(object_id="u1")
    await p.on_before_llm(ctx)
    assert len(slept) == 1                # 思考延迟 sleep 一次
    assert 3.0 <= slept[0] <= 5.0         # 默认 reply_delay 3000-5000ms
