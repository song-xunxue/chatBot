"""
sticker_plus 表情包挑选器(纯逻辑,可单测)
按"心情过滤收窄 → 描述词重叠打分 → 最近使用降权 → 并列随机"从表情包库挑一张最贴合
回复的图,每步的信息拼进 reason 短串返回(可解释:日志/面板能看到为何选它)。
供 plugin.py 自动配图调用;库数据复用 sticker_store(mychat:sticker:lib + STICKER_DIR)。

作者: 李文煜
日期: 2026-10-25

2026-10-25
变更说明：
  1. 新建:parse_mood_keywords(档位附加关键词解析,容错)/ _bigrams(中英文数字二元组)/
     pick_sticker(可解释挑选主入口:心情收窄+bigram 重叠+recent_usage 降权+并列随机)
"""
import random
import re

from storage.sticker_store import _K_LIB, STICKER_DIR   # 库 Hash(文件名→描述)与库目录,出站匹配同源

# 最近使用队列(List:文件名,最新在前)。本模块读(降权),plugin.py 写(lpush+ltrim);
# 字面量契约(render._K_LAST_USED 同款风格,两侧注释互相指认)
_K_RECENT_USAGE = "mychat:sticker:recent_usage"

# 打 bigram 前保留的字符:小写字母/数字(先 casefold)/中文基本区;其余(标点/空白/emoji)剔除
_KEEP_RE = re.compile(r"[^0-9a-z一-鿿]")


def parse_mood_keywords(s: str) -> dict[str, list[str]]:
    """解析"档位:词,词;档位:词"为 {档位: [词]}。
    容错:空段/缺冒号的段直接跳过;词去空白、去重;同档位多段合并;只有档位没有词不留空占位。
    冒号兼容半角/全角(:/：),逗号兼容半角/全角(,/，)——面板手输常见混用。"""
    out: dict[str, list[str]] = {}
    for seg in re.split(r"[;；]", s or ""):   # 分段兼容半角/全角分号(中文输入法常见混用)
        seg = seg.strip()
        if not seg:
            continue
        # 档位与词表以首个冒号分隔(半角/全角均可);缺冒号跳过该段
        idx = next((i for i, ch in enumerate(seg) if ch in (":", "：")), -1)
        if idx < 0:
            continue
        label = seg[:idx].strip()
        if not label:
            continue
        words = out.setdefault(label, [])
        for w in re.split(r"[,，]", seg[idx + 1:]):   # re.split(模式, 串):按半/全角逗号切词表
            w = w.strip()
            if w and w not in words:
                words.append(w)
    return {k: v for k, v in out.items() if v}   # 去掉只有档位没有词的空占位


def _bigrams(s: str) -> set[str]:
    """取二元组集合:先 casefold 并剔除非中文/字母/数字字符,再取相邻两字符组。
    用于"回复↔描述词重叠"打分——单字重叠噪声大,二元组更稳。"""
    cleaned = _KEEP_RE.sub("", (s or "").casefold())   # sub("", ...):把不保留的字符全部删掉
    return {cleaned[i:i + 2] for i in range(len(cleaned) - 1)}


async def pick_sticker(redis, reply_text: str, *, mood_label: str = "",
                       mood_keywords: str = "", mood_weight_enable: bool = True,
                       usage_window: int = 10,
                       rng=random.random) -> tuple[str | None, str | None, str]:
    """从表情包库挑一张最贴合回复的(可解释打分)。

    参数:
      redis: 库/最近使用队列数据源;reply_text: 待配图的回复文本
      mood_label: 当前心情档位名(空=不过滤);mood_keywords: "档位:词,词"附加关键词
      mood_weight_enable: 是否按心情过滤;usage_window: 最近使用降权窗口条数
      rng: [0,1) 随机源(默认 random.random;测试注入 lambda:0 固定选并列第一个)
    返回: (描述, 文件名, reason);库不可用时前两项为 None,reason 为中文原因。"""
    # 1. 候选:描述非空且文件存在(文件被清理过的死条目跳过);按文件名排序保证确定性
    lib = await redis.hgetall(_K_LIB)
    if not lib:
        return None, None, "库为空"
    cands = sorted(
        ((fname, (desc or "").strip()) for fname, desc in lib.items()
         if (desc or "").strip() and (STICKER_DIR / fname).exists()),
        key=lambda x: x[0],
    )
    if not cands:
        return None, None, "库内无可用表情包(描述缺失或文件不存在)"
    pool = len(cands)   # 心情过滤前的有效候选数(reason 分母)
    # 2. 心情过滤:desc 含任一关键词(casefold 子串)即命中 → 收窄;无命中回退全库
    parts: list[str] = []
    if mood_weight_enable and mood_label:
        kws = [k.casefold() for k in
               [mood_label] + parse_mood_keywords(mood_keywords).get(mood_label, []) if k]
        hits = [(f, d) for f, d in cands if any(k in d.casefold() for k in kws)]
        if hits:
            cands = hits
            parts.append(f"心情过滤[{mood_label}]候选{len(hits)}/{pool}")
        else:
            parts.append(f"心情过滤[{mood_label}]无命中回退全库")
    else:
        parts.append(f"心情过滤[{'已关闭' if not mood_weight_enable else '无档位'}]")
    # 3. 重叠打分:回复与描述的 bigram 交集大小(词重叠越多越贴)
    reply_bg = _bigrams(reply_text)
    # 4. 最近使用降权:队列第 i 位(0=最新)扣 (usage_window - i) * 0.5,刚用过的扣最重
    recent_rank: dict[str, int] = {}
    if usage_window > 0:
        # lrange(键, 起, 止):取窗口内文件名(最新在前);重复项记首次位次
        for i, fname in enumerate(await redis.lrange(_K_RECENT_USAGE, 0, usage_window - 1)):
            recent_rank.setdefault(fname, i)
    # 5. 打分取最大;同分并列时 rng() 在并列集合(按文件名稳定排序)中随机选一个
    scored: list[tuple[float, str, str, float]] = []   # (总分, 文件名, 描述, 降权)
    for fname, desc in cands:
        score = float(len(reply_bg & _bigrams(desc)))
        penalty = (usage_window - recent_rank[fname]) * 0.5 if fname in recent_rank else 0.0
        scored.append((score - penalty, fname, desc, penalty))
    top = max(s[0] for s in scored)
    tied = sorted((s for s in scored if s[0] == top), key=lambda s: s[1])
    idx = min(int(rng() * len(tied)), len(tied) - 1)   # rng()=0 恒选并列第一个(测试口径)
    total, fname, desc, penalty = tied[idx]
    # 6. reason 紧凑中文串:描述胜出路径(重叠为降权前原始分,降权为胜者自身被扣的分)
    parts.append(f"重叠{int(round(total + penalty))}")
    parts.append(f"降权-{penalty:g}")
    return desc, fname, ";".join(parts)
