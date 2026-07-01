"""
QQ 回复安全守卫(2026-07-02,架构 #3 软失败不变量)
在"发往 QQ 用户"这个出口缝隙做结构性兜底:回复命中原始错误模式(堆栈/限流/内部 URL/异常类名)
→ 降级为拟人化兜底,绝不把异常派生文本发给用户。

背景:tool-loop/工具失败/LLM 调用异常等上游软失败点各自决定降级字符串,其中"把错误塞进回复文本"
的策略曾导致 QQ 用户收到 "工具循环调用失败: Client error '429...bigmodel.cn...'"。上游各点策略难穷尽,
本模块在出口统一拦截,作为"原始错误绝不流到 QQ 用户"这条不变量的结构性保证(不依赖上游)。

作者: 李文煜
日期: 2026-07-02
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


def sanitize_reply(text: str) -> str:
    """回复安全守卫:命中错误模式 → 记录原文本(排障)+ 返回拟人化兜底;否则原样返回。
    这是 QQ 出口的软失败不变量守卫,调用方在 send_c2c_message 前调用。"""
    if looks_like_error(text):
        logger.warning("回复命中错误模式,降级兜底(原回复前 200 字符):%.200s", text)
        return _FALLBACK
    return text
