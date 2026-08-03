"""
用户称呼自动学习(2026-07-07 拟人化)
从用户消息正则提取自报称呼(叫我X/我叫X/你可以叫我X),供角色全链路用具体称呼代替"用户"。
正则免 LLM 成本;命中即更新人设 user_alias(最新自报覆盖)。误匹配由面板手动编辑兜底。

设计:
  - 单条文本提取 extract_user_alias:多模式匹配,取首个非黑名单结果
  - 消息列表学习 learn_user_alias_from_messages:倒序扫 user 消息(最近优先)
  - 黑名单:常见误捕词(外卖/老师/同学等),正则可能误匹配时兜底
  - 称呼长度 1-8 字,限中文/英文/间隔号(·),排除标点

作者: 李文煜
日期: 2026-07-07
"""
import re

# 自报称呼模式(用户主动告知角色怎么称呼自己)。捕获组:称呼本体
# 顺序:长模式优先(你可以叫我 > 叫我),避免短模式先吃掉
_ALIAS_PATTERN = re.compile(
    r"(?:你可以叫我|你可以喊我|你可以称呼我|叫我|喊我|称呼我|我叫|名字叫|名叫|本名叫|我的名字(?:是|叫))"
    r"([一-龥A-Za-z·]{1,8})"
)

# 误匹配黑名单(正则可能误捕的常见词)
_BLACKLIST = {
    "外卖", "老师", "同学", "老板", "师傅", "医生", "司机", "阿姨",
    "叔叔", "哥哥", "姐姐", "弟弟", "妹妹", "宝贝", "亲爱的",
}


def extract_user_alias(text: str) -> str | None:
    """从单条文本正则提取用户自报称呼。命中返清洗后称呼,否则 None。
    多模式匹配取首个非黑名单结果(长度 1-8)。"""
    if not text:
        return None
    for m in _ALIAS_PATTERN.finditer(text):
        alias = m.group(1).strip().rstrip("吧了啊呀哦的呢吗!！。.,，?？~")
        if alias and alias not in _BLACKLIST and 1 <= len(alias) <= 8:
            return alias
    return None


def learn_user_alias_from_messages(messages) -> str | None:
    """从消息列表扫描 user 消息(最近优先),返回首个命中的自报称呼。无命中返 None。
    messages: list[Message 或 dict],取 role=='user' 的 content。"""
    if not messages:
        return None
    for m in reversed(list(messages)):
        if isinstance(m, dict):
            role = m.get("role", "")
            content = m.get("content", "")
        else:
            role = getattr(m, "role", "")
            content = getattr(m, "content", "")
        if role != "user":
            continue
        alias = extract_user_alias(content)
        if alias:
            return alias
    return None
