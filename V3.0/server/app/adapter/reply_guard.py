"""
QQ 回复安全守卫(2026-07-02,架构 #3 软失败不变量;V3.0 2026-08-17 加句号铁律)
在"发往 QQ 用户"这个出口缝隙做结构性兜底:回复命中原始错误模式(堆栈/限流/内部 URL/异常类名)
→ 降级为拟人化兜底,绝不把异常派生文本发给用户。
2026-08-17:加 strip_trailing_period——句末句号确定性剥除(人设铁律"绝不用句号",
prompt 契约偶发违反时的出口兜底;只剥句末,不动正文中间与问叹/省略号)。

背景:tool-loop/工具失败/LLM 调用异常等上游软失败点各自决定降级字符串,其中"把错误塞进回复文本"
的策略曾导致 QQ 用户收到 "工具循环调用失败: Client error '429...bigmodel.cn...'"。上游各点策略难穷尽,
本模块在出口统一拦截,作为"原始错误绝不流到 QQ 用户"这条不变量的结构性保证(不依赖上游)。

作者: 李文煜
日期: 2026-07-02

2026-08-17
变更说明：
  1. V3.0:新增 strip_trailing_period + sanitize_reply 内置调用(机器产出统一剥句末句号)
"""
import logging
import re

logger = logging.getLogger(__name__)

# 原始错误签名(堆栈/HTTP 错误/限流/内部 API URL/已知错误前缀)——命中即视为"不该发给用户"的文本。
# 不收录"图片解析失败/搜索失败"这类**已优雅化**的用户向兜底(它们不是原始错误)。
_ERROR_PATTERNS = [
    re.compile(r"Traceback \(most recent call last\)"),          # Python 堆栈
    re.compile(r"httpx\.HTTPStatusError|HTTPStatusError"),       # httpx 异常类名
    re.compile(r"Client error '\d{3}"),                           # httpx 4xx/5xx 前缀
    re.compile(r"Server error '\d{3}"),
    re.compile(r"Too Many Requests"),                             # 限流
    re.compile(r"工具循环调用失败"),                              # tool-loop 旧 bug 串
    re.compile(r"for url 'https?://"),                            # httpx 错误附 URL
    re.compile(r"open\.bigmodel\.cn|api\.deepseek\.com|api\.sgroup\.qq\.com|/api/paas/v4"),  # 内部 URL
]

# 拟人化兜底(替代错误堆栈;角色口吻,不暴露技术细节)
_FALLBACK = "（刚刚走神啦，能再说一次吗～）"


def looks_like_error(text: str) -> bool:
    """文本是否命中原始错误签名(空串不算)"""
    if not text:
        return False
    return any(p.search(text) for p in _ERROR_PATTERNS)


def strip_trailing_period(text: str) -> str:
    """句号铁律(2026-08-17):剥除句末句号(可多个)。只动句末——正文中间的句号由
    OUTPUT_CONTRACT 约束(出口强剥会破坏语义);问号/叹号/省略号/波浪号不动。
    小数保护:ASCII '.' 前一个字符是数字则视为小数(如"3.5")不剥。"""
    if not text:
        return text
    out = text.rstrip()
    while out and out[-1] in "。.":
        if out[-1] == "." and len(out) >= 2 and out[-2].isdigit():
            break   # 小数(3.5 类)不剥
        out = out[:-1]
    return out


def sanitize_reply(text: str) -> str:
    """回复安全守卫:命中错误模式 → 记录原文本(排障)+ 返回拟人化兜底;否则剥句末句号后返回。
    QQ 出口的软失败不变量守卫——由 adapter.send_text 在内部对机器产出内容默认调用
    (human_authored=False);人类手打代答(human_authored=True)显式跳过(含句号铁律,尊重 admin 原文)。"""
    if looks_like_error(text):
        logger.warning("回复命中错误模式,降级兜底(原回复前 200 字符):%.200s", text)
        return _FALLBACK
    return strip_trailing_period(text)
