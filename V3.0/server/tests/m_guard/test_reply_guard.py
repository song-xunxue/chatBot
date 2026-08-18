"""
QQ 回复安全守卫单测(2026-07-02,架构 #3)
钉死不变量:"原始错误文本绝不流到 QQ 用户"。错误签名(堆栈/限流/内部URL/异常类名/旧 bug 串)→降级兜底;
正常回复 + 已优雅化的用户向兜底(如"图片解析失败")原样放行。

作者: 李文煜
日期: 2026-07-02
"""
from adapter.reply_guard import sanitize_reply, looks_like_error


def test_normal_reply_passes_through():
    """正常拟人化回复原样通过"""
    assert sanitize_reply("你好呀，今天我也很想你～") == "你好呀，今天我也很想你～"
    assert looks_like_error("随便聊点什么吧") is False


def test_original_bug_string_sanitized():
    """#3 起源 bug:tool-loop 429 错误堆栈当回复 → 必须降级"""
    bug = "(工具循环调用失败: Client error '429 Too Many Requests' for url 'https://open.bigmodel.cn/api/paas/v4/chat/completions')"
    out = sanitize_reply(bug)
    assert out != bug
    assert "429" not in out and "bigmodel" not in out and "工具循环" not in out


def test_traceback_sanitized():
    assert "Traceback" not in sanitize_reply("Traceback (most recent call last)\n  File x.py")
    assert looks_like_error("Traceback (most recent call last)") is True


def test_internal_url_sanitized():
    assert "deepseek" not in sanitize_reply("出错: https://api.deepseek.com/chat/completions 返回 500")
    assert looks_like_error("https://api.sgroup.qq.com/v2/users/x") is True


def test_httpstatuserror_sanitized():
    assert "HTTPStatusError" not in sanitize_reply("httpx.HTTPStatusError: Server error '500'")
    assert looks_like_error("Client error '429") is True


def test_graceful_fallback_passes():
    """已优雅化的用户向兜底(图片解析失败提示)不是原始错误,放行(不误杀)"""
    graceful = "[用户发了一张图片,但解析失败]"
    assert sanitize_reply(graceful) == graceful
    assert looks_like_error(graceful) is False


def test_empty_passes():
    assert sanitize_reply("") == ""
    assert looks_like_error("") is False


def test_fallback_is_in_character():
    """降级文本是拟人化口吻,不含技术细节"""
    out = sanitize_reply("Traceback (most recent call last)")
    assert "Traceback" not in out
    assert len(out) > 0


# —— 句号铁律(2026-08-17 V3.0):出口确定性剥句末句号 ——
from adapter.reply_guard import strip_trailing_period


def test_strip_trailing_period_chinese():
    """句末全角句号剥除(单个/多个/带尾空白)"""
    assert strip_trailing_period("今天好累。") == "今天好累"
    assert strip_trailing_period("嗯。。") == "嗯"
    assert strip_trailing_period("晚安~ ") == "晚安~"          # 尾空白剥但波浪号保留


def test_strip_trailing_period_keeps_others():
    """问叹/省略号/正文中间句号不动"""
    assert strip_trailing_period("真的吗？") == "真的吗？"
    assert strip_trailing_period("好呀!") == "好呀!"
    assert strip_trailing_period("等你…") == "等你…"
    assert strip_trailing_period("早。你吃了吗") == "早。你吃了吗"   # 中间句号保留(契约管)


def test_strip_trailing_period_decimal_protected():
    """小数保护:'3.5' 结尾的 ASCII 点不剥"""
    assert strip_trailing_period("考了3.5") == "考了3.5"
    assert strip_trailing_period("ok.") == "ok"                 # 非数字前缀的 . 剥


def test_sanitize_strips_period_on_clean_text():
    """sanitize_reply 对干净文本剥句末句号(机器产出统一过铁律)"""
    out = sanitize_reply("今天也要开心哦。")
    assert out == "今天也要开心哦"
