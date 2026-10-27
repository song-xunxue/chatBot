"""
sticker_plus 插件单测
覆盖:picker 纯函数(parse_mood_keywords/_bigrams)与 pick_sticker 全算法分支
(心情收窄/回退全库/关闭、bigram 重叠胜出、并列随机、recent_usage 降权翻盘与 reason 降权值、
空库、文件缺失与空描述跳过);on_message_out 链路(追加 token+记使用/概率门/排除链三连/
心情 label 透传/inject_hint 异常软失败/usage_window 裁剪);render_text_sticker
(落盘+注册+幂等/空与超长 ValueError);plugin.yaml manifest 校验。

日期: 2026-10-25

2026-10-25
变更说明：
  1. 新增 sticker_plus 插件测试(picker 纯函数 + on_message_out 链路 + render + manifest)
"""
from pathlib import Path

import pytest

import plugins.sticker_plus.picker as picker
import plugins.sticker_plus.plugin as sp
import plugins.sticker_plus.render as render_mod
from pipeline.context import MessageContext
from plugins.base import HookResult, PluginContext
from plugins.manifest import PluginManifest, parse_manifest
from plugins.sticker_plus.picker import _K_RECENT_USAGE, _bigrams, parse_mood_keywords, pick_sticker
from plugins.sticker_plus.plugin import StickerPlusPlugin
from plugins.sticker_plus.render import _K_LAST_USED, render_text_sticker
from storage.sticker_store import _K_LIB, _REPLY_TOKEN_RE

# 三张测试库:开心/难过/微笑系描述,各自 bigram 互不重叠(便于精确断言打分)
_LIB3 = {"happy.png": "开心猫咪举爪", "sad.png": "难过落泪哭泣", "smile.png": "微笑打招呼"}

# on_message_out 测试基准参数(概率 1 保证确定性)
_PARAMS = {"attach_prob": 1.0, "mood_weight_enable": True, "mood_keywords": "",
           "usage_window": 10}


class _FakeManager:
    """轻量 mock:get_params 返回构造时指定的参数(不走 config_schema 合并,测试显式给全)"""

    def __init__(self, params=None):
        self._params = params or {}

    async def get_params(self, name, oid):
        return dict(self._params)


def _make_plugin(params=None, redis=None):
    """构造插件实例(m6 惯例:手写 pctx 注入,不经 PluginManager)"""
    p = StickerPlusPlugin()
    p.manifest = PluginManifest(name="sticker_plus")
    p.pctx = PluginContext(manager=_FakeManager(params), redis=redis,
                           settings=None, manifest=p.manifest)
    return p


async def _seed_lib(fake_redis, tmp_path, monkeypatch, entries, *, skip_files=()):
    """注册表情包库并造假文件(内容随意,picker 只查存在性);skip_files 名单不落盘"""
    monkeypatch.setattr(picker, "STICKER_DIR", tmp_path)
    for fname in entries:
        if fname not in skip_files:
            (tmp_path / fname).write_bytes(b"x")
    if entries:   # 空 mapping 的 hset 会报 DataError,空库场景直接不注册
        await fake_redis.hset(_K_LIB, mapping=entries)


# ================ 纯函数:parse_mood_keywords / _bigrams ================

def test_parse_mood_keywords_normal():
    """正常解析:分号分段、冒号分档、逗号分词"""
    assert parse_mood_keywords("开心:哈哈,雀跃;难过:呜呜") == {
        "开心": ["哈哈", "雀跃"], "难过": ["呜呜"]}


def test_parse_mood_keywords_tolerant():
    """容错:空串/空段跳过;缺冒号段跳过;词去空白去重;同档位多段合并;全角兼容;只档位无词不占位"""
    assert parse_mood_keywords("") == {}
    assert parse_mood_keywords(";; ;") == {}
    assert parse_mood_keywords("没有冒号的段;开心:笑") == {"开心": ["笑"]}
    assert parse_mood_keywords(" 开心 : 哈哈 , 哈哈 ,笑 ") == {"开心": ["哈哈", "笑"]}
    assert parse_mood_keywords("开心:雀跃;开心:笑") == {"开心": ["雀跃", "笑"]}
    assert parse_mood_keywords("开心：全角冒号,，全角逗号") == {"开心": ["全角冒号", "全角逗号"]}
    assert parse_mood_keywords("开心:") == {}


def test_bigrams():
    """casefold + 剔除非中文/字母/数字后取二元组;单字符/空串为空集"""
    assert _bigrams("开心猫") == {"开心", "心猫"}
    assert _bigrams("A b-c!") == _bigrams("abc") == {"ab", "bc"}
    assert _bigrams("!") == set()
    assert _bigrams("") == set()


# ================ pick_sticker ================

async def test_pick_sticker_empty_lib(fake_redis):
    """空库(未注册任何条目):返回 (None, None, 库为空)"""
    desc, fname, reason = await pick_sticker(fake_redis, "你好呀")
    assert desc is None and fname is None and reason == "库为空"


async def test_pick_sticker_missing_file_and_blank_desc_skipped(fake_redis, tmp_path, monkeypatch):
    """文件不存在的死条目与空描述条目被跳过:即使重叠分更高也不选,只从落盘条目里挑"""
    await _seed_lib(fake_redis, tmp_path, monkeypatch,
                    {"gone.png": "开心开心开心", "here.png": "平静", "blank.png": ""},
                    skip_files=("gone.png",))
    desc, fname, reason = await pick_sticker(fake_redis, "开心开心开心", rng=lambda: 0)
    assert fname == "here.png" and desc == "平静"


async def test_pick_sticker_mood_narrows(fake_redis, tmp_path, monkeypatch):
    """心情过滤收窄:回复语义更贴'难过',但档位=开心 → 命中集只剩 happy,必选之"""
    await _seed_lib(fake_redis, tmp_path, monkeypatch, dict(_LIB3))
    desc, fname, reason = await pick_sticker(fake_redis, "呜呜我好难过想哭", mood_label="开心")
    assert fname == "happy.png" and desc == "开心猫咪举爪"
    assert "心情过滤[开心]候选1/3" in reason


async def test_pick_sticker_mood_fallback_all(fake_redis, tmp_path, monkeypatch):
    """心情无命中回退全库:档位=生气无人命中,按重叠分正常选(sad 胜出),reason 注明回退"""
    await _seed_lib(fake_redis, tmp_path, monkeypatch, dict(_LIB3))
    desc, fname, reason = await pick_sticker(fake_redis, "呜呜我好难过想哭", mood_label="生气")
    assert fname == "sad.png"
    assert "心情过滤[生气]无命中回退全库" in reason


async def test_pick_sticker_mood_disabled(fake_redis, tmp_path, monkeypatch):
    """mood_weight_enable=False:即使有档位也不过滤,直接按重叠分选,reason 注明已关闭"""
    await _seed_lib(fake_redis, tmp_path, monkeypatch, dict(_LIB3))
    desc, fname, reason = await pick_sticker(fake_redis, "呜呜我好难过想哭",
                                             mood_label="开心", mood_weight_enable=False)
    assert fname == "sad.png"
    assert "心情过滤[已关闭]" in reason


async def test_pick_sticker_mood_keywords_extra(fake_redis, tmp_path, monkeypatch):
    """附加关键词扩候选:档位'开心'本身只命中 happy,加'雀跃'后 jump 入围并按重叠分胜出"""
    await _seed_lib(fake_redis, tmp_path, monkeypatch,
                    {"happy.png": "开心猫咪举爪", "jump.png": "小兔雀跃蹦跳"})
    desc, fname, reason = await pick_sticker(fake_redis, "小兔子蹦蹦跳跳真雀跃",
                                             mood_label="开心", mood_keywords="开心:雀跃")
    assert fname == "jump.png"
    assert "心情过滤[开心]候选2/2" in reason


async def test_pick_sticker_overlap_wins(fake_redis, tmp_path, monkeypatch):
    """重叠打分胜出:desc 与回复共享 bigram 多者赢(2 分压 0 分)"""
    await _seed_lib(fake_redis, tmp_path, monkeypatch,
                    {"laugh.png": "开心哈哈大笑", "sleep.png": "睡觉休息晚安"})
    desc, fname, reason = await pick_sticker(fake_redis, "今天真的好开心呀哈哈哈")
    assert fname == "laugh.png"
    assert "重叠2" in reason


async def test_pick_sticker_tie_rng(fake_redis, tmp_path, monkeypatch):
    """同分并列:rng()=0 选并列第一个(文件名排序);rng()=0.99/1.0 选最后一个(越界钳制)"""
    await _seed_lib(fake_redis, tmp_path, monkeypatch,
                    {"a.png": "开心笑", "b.png": "开心哭"})
    _, fname, _ = await pick_sticker(fake_redis, "开心", rng=lambda: 0)
    assert fname == "a.png"
    _, fname, _ = await pick_sticker(fake_redis, "开心", rng=lambda: 0.99)
    assert fname == "b.png"
    _, fname, _ = await pick_sticker(fake_redis, "开心", rng=lambda: 1.0)
    assert fname == "b.png"


async def test_pick_sticker_recent_penalty_flips(fake_redis, tmp_path, monkeypatch):
    """最近使用降权:把高分者(重叠2)lpush 进窗口,扣 10*0.5=5 分 → 低分者(1)翻盘"""
    await _seed_lib(fake_redis, tmp_path, monkeypatch,
                    {"hi.png": "开心哈哈大笑", "lo.png": "开心微笑一下"})
    await fake_redis.lpush(_K_RECENT_USAGE, "hi.png")
    desc, fname, reason = await pick_sticker(fake_redis, "今天真的好开心呀哈哈哈", usage_window=10)
    assert fname == "lo.png" and desc == "开心微笑一下"
    assert "重叠1" in reason and "降权-0" in reason


async def test_pick_sticker_recent_penalty_in_reason(fake_redis, tmp_path, monkeypatch):
    """窗口 1 条:高分者(重叠2)被降权 0.5 后仍以 1.5 分胜出,reason 如实记 降权-0.5/重叠2"""
    await _seed_lib(fake_redis, tmp_path, monkeypatch,
                    {"hi.png": "开心哈哈大笑", "lo.png": "开心微笑一下"})
    await fake_redis.lpush(_K_RECENT_USAGE, "hi.png")
    desc, fname, reason = await pick_sticker(fake_redis, "今天真的好开心呀哈哈哈", usage_window=1)
    assert fname == "hi.png"
    assert "重叠2" in reason and "降权-0.5" in reason


# ================ on_message_out 链路 ================

async def test_on_message_out_attaches(fake_redis, tmp_path, monkeypatch):
    """attach_prob=1:token 追加成功 + recent_usage/last_used 已记(走真实 inject_hint,无档位 label)"""
    await _seed_lib(fake_redis, tmp_path, monkeypatch,
                    {"laugh.png": "开心哈哈大笑", "sleep.png": "睡觉休息晚安"})
    p = _make_plugin(dict(_PARAMS), redis=fake_redis)
    ctx = MessageContext(object_id="10001", reply_text="哈哈哈哈笑死我了")
    result = await p.on_message_out(ctx)
    assert result is HookResult.CONTINUE
    assert ctx.reply_text == "哈哈哈哈笑死我了\n[表情包: 开心哈哈大笑]"
    assert await fake_redis.lrange(_K_RECENT_USAGE, 0, -1) == ["laugh.png"]
    assert await fake_redis.hget(_K_LAST_USED, "laugh.png")


async def test_on_message_out_mood_label_passthrough(fake_redis, tmp_path, monkeypatch):
    """心情 label 透传:inject_hint 返回'开心' → 收窄到 happy(压过重叠更高的 sad)"""
    await _seed_lib(fake_redis, tmp_path, monkeypatch,
                    {"happy.png": "开心猫咪举爪", "sad.png": "难过落泪哭泣"})

    async def fake_inject(redis, oid):
        return {"mood": 0.9, "hint": "", "label": "开心", "kaomoji": ""}

    monkeypatch.setattr(sp, "inject_hint", fake_inject)
    p = _make_plugin(dict(_PARAMS), redis=fake_redis)
    ctx = MessageContext(object_id="10001", reply_text="呜呜我好难过想哭")
    await p.on_message_out(ctx)
    assert ctx.reply_text == "呜呜我好难过想哭\n[表情包: 开心猫咪举爪]"


async def test_on_message_out_prob_zero_never_attaches(fake_redis, tmp_path, monkeypatch):
    """attach_prob=0:永不配图,不改文本不写使用记录"""
    await _seed_lib(fake_redis, tmp_path, monkeypatch, dict(_LIB3))
    p = _make_plugin({**_PARAMS, "attach_prob": 0.0}, redis=fake_redis)
    ctx = MessageContext(object_id="10001", reply_text="哈哈哈哈笑死我了")
    await p.on_message_out(ctx)
    assert ctx.reply_text == "哈哈哈哈笑死我了"
    assert await fake_redis.lrange(_K_RECENT_USAGE, 0, -1) == []


async def test_on_message_out_blank_text_skips(fake_redis):
    """空白回复跳过(无从配图)"""
    p = _make_plugin(dict(_PARAMS), redis=fake_redis)
    ctx = MessageContext(object_id="10001", reply_text="   ")
    result = await p.on_message_out(ctx)
    assert result is HookResult.CONTINUE
    assert ctx.reply_text == "   "


async def test_on_message_out_existing_token_skips(fake_redis, tmp_path, monkeypatch):
    """本条已有表情包 token:最多 1 张/条,不再追加"""
    await _seed_lib(fake_redis, tmp_path, monkeypatch, dict(_LIB3))
    p = _make_plugin(dict(_PARAMS), redis=fake_redis)
    raw = "早上好呀\n[表情包: 开心猫咪]"
    ctx = MessageContext(object_id="10001", reply_text=raw)
    await p.on_message_out(ctx)
    assert ctx.reply_text == raw
    assert await fake_redis.lrange(_K_RECENT_USAGE, 0, -1) == []


async def test_on_message_out_reply_sent_skips(fake_redis, tmp_path, monkeypatch):
    """reply_sent=True(TTS/分段已发):再改文本无效,直接跳过"""
    await _seed_lib(fake_redis, tmp_path, monkeypatch, dict(_LIB3))
    p = _make_plugin(dict(_PARAMS), redis=fake_redis)
    ctx = MessageContext(object_id="10001", reply_text="你好呀", reply_sent=True)
    await p.on_message_out(ctx)
    assert ctx.reply_text == "你好呀"
    assert await fake_redis.lrange(_K_RECENT_USAGE, 0, -1) == []


async def test_on_message_out_inject_hint_raises_still_attaches(fake_redis, tmp_path, monkeypatch):
    """inject_hint 抛异常:warning 后当无心情处理,不炸、照常配图、恒 CONTINUE"""
    await _seed_lib(fake_redis, tmp_path, monkeypatch,
                    {"laugh.png": "开心哈哈大笑", "sleep.png": "睡觉休息晚安"})

    async def boom(redis, oid):
        raise RuntimeError("mood boom")

    monkeypatch.setattr(sp, "inject_hint", boom)
    p = _make_plugin(dict(_PARAMS), redis=fake_redis)
    ctx = MessageContext(object_id="10001", reply_text="哈哈哈哈笑死我了")
    result = await p.on_message_out(ctx)
    assert result is HookResult.CONTINUE
    assert _REPLY_TOKEN_RE.search(ctx.reply_text)


async def test_on_message_out_empty_lib_no_token(fake_redis, tmp_path, monkeypatch):
    """库为空:不追加 token 不写使用记录(软跳过,恒 CONTINUE)"""
    await _seed_lib(fake_redis, tmp_path, monkeypatch, {})
    p = _make_plugin(dict(_PARAMS), redis=fake_redis)
    ctx = MessageContext(object_id="10001", reply_text="哈哈哈哈笑死我了")
    result = await p.on_message_out(ctx)
    assert result is HookResult.CONTINUE
    assert ctx.reply_text == "哈哈哈哈笑死我了"
    assert await fake_redis.lrange(_K_RECENT_USAGE, 0, -1) == []


async def test_on_message_out_usage_window_trims(fake_redis, tmp_path, monkeypatch):
    """usage_window=1:连续两条配图后 recent_usage 只保留 1 条(ltrim 生效)"""
    await _seed_lib(fake_redis, tmp_path, monkeypatch,
                    {"laugh.png": "开心哈哈大笑", "sleep.png": "睡觉休息晚安"})
    p = _make_plugin({**_PARAMS, "usage_window": 1}, redis=fake_redis)
    for _ in range(2):
        ctx = MessageContext(object_id="10001", reply_text="哈哈哈哈笑死我了")
        await p.on_message_out(ctx)
    assert await fake_redis.lrange(_K_RECENT_USAGE, 0, -1) == ["laugh.png"]


# ================ render_text_sticker(共享模块 render.py) ================

async def test_render_text_sticker_generates(fake_redis, tmp_path, monkeypatch):
    """生成:PNG 落盘(魔数校验)+ hset lib 注册 + token 格式正确 + last_used 已记"""
    monkeypatch.setattr(render_mod, "STICKER_DIR", tmp_path)
    out = await render_text_sticker(fake_redis, " 笑死我了 ")
    assert out["desc"] == "笑死我了"
    assert out["token"] == "[表情包: 笑死我了]"
    path = tmp_path / out["file"]
    assert path.exists()
    assert path.read_bytes()[:8] == bytes.fromhex("89504e470d0a1a0a")   # PNG 魔数
    assert await fake_redis.hget(_K_LIB, out["file"]) == "笑死我了"
    assert await fake_redis.hget(_K_LAST_USED, out["file"])


async def test_render_text_sticker_idempotent(fake_redis, tmp_path, monkeypatch):
    """幂等:同文字同底图两次调用生成同名文件(内容覆盖,不堆重复文件)"""
    monkeypatch.setattr(render_mod, "STICKER_DIR", tmp_path)
    out1 = await render_text_sticker(fake_redis, "笑死我了")
    out2 = await render_text_sticker(fake_redis, "笑死我了")
    assert out1["file"] == out2["file"]
    assert [p.name for p in tmp_path.iterdir()] == [out1["file"]]


async def test_render_text_sticker_invalid_input(fake_redis, tmp_path, monkeypatch):
    """空文本/41 字超限:抛 ValueError(token 描述上限 40 字)"""
    monkeypatch.setattr(render_mod, "STICKER_DIR", tmp_path)
    with pytest.raises(ValueError):
        await render_text_sticker(fake_redis, "  ")
    with pytest.raises(ValueError):
        await render_text_sticker(fake_redis, "字" * 41)


# ================ manifest ================

def test_manifest_default_disabled_and_hooks():
    """plugin.yaml 解析:默认关闭 + 只声明 on_message_out(优先级 350)+ 9 个配置键齐备"""
    yaml_path = (Path(__file__).resolve().parents[2] / "app" / "plugins"
                 / "sticker_plus" / "plugin.yaml")
    m = parse_manifest(yaml_path)
    assert m.name == "sticker_plus"
    assert m.default_enabled is False
    assert m.hook_names == ["on_message_out"]
    assert m.hooks[0].priority == 350
    for key in ("attach_prob", "mood_weight_enable", "mood_keywords", "usage_window",
                "render_template", "render_font", "render_font_size", "render_stroke",
                "render_position"):
        assert key in m.config_schema, key


# ================ 审查加固回归(2026-10-25) ================

def test_parse_mood_keywords_fullwidth_semicolon():
    """全角分号分段(中文输入法常见)与半角等效——审查低#1 回归"""
    assert parse_mood_keywords("开心:哈哈；难过:呜呜") == {"开心": ["哈哈"], "难过": ["呜呜"]}
