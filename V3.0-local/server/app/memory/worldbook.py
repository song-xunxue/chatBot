"""
世界书式记忆 · 纯逻辑(docs/09 §1-§2)
Entry 模型 + keys 归一化匹配(大小写/全半角) + key_regex/secondary_keys +
候选收集 + 过滤(enabled/冷却/概率) + 排序(position/order/weight/久未命中) +
预算裁剪(always 永不裁 + 前 3 条 trigger 保底) + 分 position 渲染。
零 IO 依赖(不碰 Redis/LLM),供 worldbook_store(存储)/worldbook_runtime(注入)复用,单测友好。

日期: 2026-10-26

2026-10-26
变更说明:
  1. 新建:WbEntry dataclass + normalize_for_match/estimate_tokens/match_entry/
     collect_candidates/filter_entries/sort_entries/budget_trim/render_sections/
     select_for_injection(一站式) + auto_keys(自动条目 keys 提取)
"""
import json
import random
import re
import time
import uuid
from dataclasses import dataclass, field, asdict

# position 合法值(注入锚点,排序分组用;docs/09 §1)
POSITIONS = ("before_persona", "after_persona", "before_memories", "after_memories", "tail")
# mode 合法值
MODES = ("trigger", "always")
# source 合法值(docs/09 §1:manual 手写设定 / 自动 memory|summary|diary|dream|roleplay)
SOURCES = ("manual", "memory", "summary", "diary", "dream", "roleplay")
# 自动来源(非 manual):rebuild 重建时按此集合清重建
AUTO_SOURCES = ("memory", "summary", "diary", "dream", "roleplay")

# 预算裁剪时 trigger 条目的保底条数(docs/09 §2.4:永远先保住 always + 前 3 条 trigger)
TRIGGER_KEEP_MIN = 3

# 全角→半角映射表(全角 ASCII U+FF01-U+FF5E ↔ 半角 U+0021-U+007E 偏移 0xFEE0;
# 全角空格 U+3000 → 半角空格),匹配前统一归一,大小写/全半角差异不再漏命中
_FW_TABLE = {i: i - 0xFEE0 for i in range(0xFF01, 0xFF5F)} | {0x3000: 0x20}


def normalize_for_match(s: str) -> str:
    """匹配归一化:全角→半角 + 大写→小写 + 去空白(docs/09 §2.1b)。
    标点保留(雷/ thunder! 这类含标点 key 少见,保留可减误连;keys 侧同口径归一)"""
    return (s or "").translate(_FW_TABLE).lower().replace(" ", "").replace("\t", "").replace("\n", "")


_CJK_RUN = re.compile(r"[一-龥]+")            # 连续汉字段(切 2-gram 用)
_WORD = re.compile(r"[a-zA-Z0-9]+")           # 英文/数字词
# 中文虚词 2-gram 停用表(自动 keys 提取时过滤,避免"我们/一个"这类无区分度的 key)
_STOPGRAM = {
    "我们", "你们", "他们", "她们", "一个", "什么", "没有", "自己", "这个", "那个",
    "时候", "现在", "可以", "就是", "但是", "因为", "所以", "如果", "还是", "已经",
    "这样", "那样", "怎么", "觉得", "感觉", "知道", "可能", "应该", "不会", "一下",
    "很多", "有些", "然后", "其实", "真的", "关于", "对于", "以及", "或者", "而且",
}


def estimate_tokens(text: str) -> int:
    """token 粗估(零依赖):汉字按 1 token/字,连续英文数字按 1.3 token/词。
    只用于注入预算的相对控制,不追求与真实 tokenizer 对齐"""
    text = text or ""
    han = len(_CJK_RUN.findall(text) and "".join(_CJK_RUN.findall(text)))
    words = len(_WORD.findall(text))
    return max(1, int(round(han + words * 1.3)))


def auto_keys(content: str, limit: int = 6) -> list[str]:
    """从记忆/摘要文本自动提取触发词(docs/09 §3:keys 由事实里的名词自动生成)。
    中文取 2-gram(去虚词停用表),英文/数字取整词(长度>=2);保序去重取前 limit"""
    content = content or ""
    keys: list[str] = []
    seen: set[str] = set()

    def _push(k: str) -> None:
        if k and k not in seen:
            seen.add(k)
            keys.append(k)

    for run in _CJK_RUN.findall(content):
        grams = [run[i:i + 2] for i in range(len(run) - 1)] or ([run] if len(run) == 1 else [])
        for g in grams:
            if g not in _STOPGRAM:
                _push(g)
    for w in _WORD.findall(content):
        if len(w) >= 2:
            _push(w.lower())
    return keys[:limit]


def new_entry_id() -> str:
    """生成条目 id(与 MemoryItem 的 mem_ 前缀风格一致)"""
    return f"wb_{uuid.uuid4().hex[:12]}"


@dataclass
class WbEntry:
    """世界书条目(docs/09 §1)。时间字段沿用项目统一口径:int Unix 毫秒(created_ts/updated_ts)"""
    id: str
    title: str = ""
    content: str = ""                              # 注入正文(1-3 句,短)
    keys: list = field(default_factory=list)       # 触发词(命中其一即候选)
    key_regex: str = ""                            # 可选正则(优先于 keys 匹配;非法视为不命中)
    secondary_keys: list = field(default_factory=list)  # 可选 AND 键(非空时须全部命中)
    mode: str = "trigger"                          # trigger=命中才注入 / always=常驻
    order: int = 100                               # 注入顺序(数字小靠前)
    position: str = "before_memories"              # 注入锚点(POSITIONS 之一)
    probability: float = 1.0                       # 命中后注入概率(0-1;always 恒注入)
    cooldown_minutes: int = 0                      # 同会话冷却(分钟;0=不冷却)
    token_estimate: int = 0                        # token 估算(0=按 content 现算)
    enabled: bool = True
    source: str = "manual"                         # manual|memory|summary|diary|dream|roleplay
    source_ref: str = ""                           # 来源 id(如 "{oid}:{mid}"),幂等 upsert/溯源用
    weight: float = 1.0                            # 衰减权重(自动条目接 useful_score,manual 恒 1)
    hits: int = 0                                  # 真实注入次数(命中未注入不计)
    last_hit_at: int = 0                           # 上次命中(含未注入)时间
    last_injected_at: int = 0                      # 上次真实注入时间(冷却基准)
    created_ts: int = 0
    updated_ts: int = 0

    def __post_init__(self):
        now = int(time.time() * 1000)
        if not self.created_ts:
            self.created_ts = now
        if not self.updated_ts:
            self.updated_ts = now
        if not self.token_estimate:
            self.token_estimate = estimate_tokens(self.content)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_redis(self) -> dict:
        """Redis hash 存储视图:list 字段 JSON 化、bool 转 int(hash 值只接受标量)"""
        d = self.to_dict()
        d["keys"] = json.dumps(d["keys"], ensure_ascii=False)
        d["secondary_keys"] = json.dumps(d["secondary_keys"], ensure_ascii=False)
        d["enabled"] = int(self.enabled)
        return d

    @staticmethod
    def _list_field(v) -> list:
        """list 字段容错读取:真 list 直过;JSON 字符串(Redis 读回)解析;其余兜底空"""
        if isinstance(v, list):
            return v
        if isinstance(v, str) and v:
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, list) else []
            except (ValueError, TypeError):
                return []
        return []

    @staticmethod
    def _bool_field(v, default: bool) -> bool:
        """bool 字段容错读取:bool 直过;int 0/1;str "0"/"1"/"true"/"false"(Redis 读回)"""
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return bool(v)
        if isinstance(v, str):
            return v.strip().lower() in ("1", "true", "yes")
        return default

    @classmethod
    def from_dict(cls, raw: dict) -> "WbEntry":
        raw = dict(raw or {})
        # 容错:非法 mode/position/source 回退默认(存储脏数据不炸注入主链路)
        mode = raw.get("mode", "trigger")
        mode = mode if mode in MODES else "trigger"
        position = raw.get("position", "before_memories")
        position = position if position in POSITIONS else "before_memories"
        source = raw.get("source", "manual")
        source = source if source in SOURCES else "manual"
        keys = WbEntry._list_field(raw.get("keys", []))
        secondary = WbEntry._list_field(raw.get("secondary_keys", []))
        return cls(
            id=raw.get("id", ""),
            title=raw.get("title", ""),
            content=raw.get("content", ""),
            keys=[str(k) for k in keys] if isinstance(keys, list) else [],
            key_regex=str(raw.get("key_regex", "") or ""),
            secondary_keys=[str(k) for k in secondary] if isinstance(secondary, list) else [],
            mode=mode,
            order=int(raw.get("order", 100)),
            position=position,
            probability=max(0.0, min(1.0, float(raw.get("probability", 1.0)))),
            cooldown_minutes=max(0, int(raw.get("cooldown_minutes", 0))),
            token_estimate=max(0, int(raw.get("token_estimate", 0))),
            enabled=WbEntry._bool_field(raw.get("enabled", True), True),
            source=source,
            source_ref=str(raw.get("source_ref", "") or ""),
            weight=max(0.0, float(raw.get("weight", 1.0))),
            hits=int(raw.get("hits", 0)),
            last_hit_at=int(raw.get("last_hit_at", 0)),
            last_injected_at=int(raw.get("last_injected_at", 0)),
            created_ts=int(raw.get("created_ts", 0)),
            updated_ts=int(raw.get("updated_ts", 0)),
        )


# ================ 匹配(docs/09 §2.1) ================

def match_entry(entry: WbEntry, texts: list[str]) -> bool:
    """trigger 条目是否命中:key_regex 优先(re.search,非法/未命中回退 keys);
    keys 归一化子串匹配(命中其一);secondary_keys 非空时须全部命中(AND)。
    texts = 当前用户消息 + 最近对话,整体拼接后归一化匹配"""
    hay = normalize_for_match(" ".join(t for t in texts if t))
    if not hay:
        return False
    # 1.key_regex 优先
    if entry.key_regex:
        try:
            if re.search(entry.key_regex, hay):
                hit = True
            else:
                hit = False
        except re.error:
            hit = False   # 非则正则视为不命中(不炸主链路)
        if hit:
            return _secondary_ok(entry, hay)
        # regex 配了但未命中:仍回退 keys 兜底(docs §1 key_regex 优先,未说排除 keys)
    # 2.keys 子串匹配(归一化双侧)
    for k in entry.keys:
        nk = normalize_for_match(k)
        if nk and nk in hay:
            return _secondary_ok(entry, hay)
    return False


def _secondary_ok(entry: WbEntry, hay: str) -> bool:
    """secondary_keys 非空时须全部命中(AND 门)"""
    for k in entry.secondary_keys:
        nk = normalize_for_match(k)
        if not nk or nk not in hay:
            return False
    return True


# ================ 收集 / 过滤 / 排序 / 裁剪 / 渲染(docs/09 §2.1-2.5) ================

def collect_candidates(entries: list[WbEntry], texts: list[str]) -> list[WbEntry]:
    """收集候选:mode=always 全收 + trigger 命中收(enabled 过滤留给 filter,这里只管候选)"""
    out = [e for e in entries if e.mode == "always"]
    out += [e for e in entries if e.mode == "trigger" and match_entry(e, texts)]
    return out


def filter_entries(entries: list[WbEntry], now_ms: int,
                   rng: random.Random | None = None) -> list[WbEntry]:
    """过滤:enabled=false 跳过 / 冷却未过跳过 / trigger 按概率保留(always 恒保留)。
    rng 可注入(测试确定性);默认 random.Random()"""
    rng = rng or random.Random()
    out = []
    for e in entries:
        if not e.enabled:
            continue
        if (e.cooldown_minutes > 0 and e.last_injected_at > 0
                and now_ms - e.last_injected_at < e.cooldown_minutes * 60_000):
            continue
        if e.mode == "trigger" and rng.random() >= e.probability:
            continue
        out.append(e)
    return out


def sort_entries(entries: list[WbEntry]) -> list[WbEntry]:
    """排序:先按 position 分组(before_persona→…→tail)→ 组内 order 升序 →
    weight 降序 → last_hit_at 升序(久未命中/从未命中优先)"""
    return sorted(entries, key=lambda e: (POSITIONS.index(e.position), e.order,
                                          -e.weight, e.last_hit_at))


def budget_trim(ordered: list[WbEntry], budget: int,
                max_entries: int = 0) -> tuple[list[WbEntry], list[WbEntry]]:
    """预算裁剪(docs/09 §2.4):依次累加 token_estimate,超 BUDGET 即停;
    always 永不被裁(验收#3)+ 排序后前 3 条 trigger 保底(无视预算)。
    max_entries>0 时再按「always 优先填充,余量给 trigger」截断条数(防 prompt 爆炸的硬顶;
    always 数量本身超顶的极端场景下 always 也截,否则「每轮最多 N 条」永不成立)。
    返回 (kept, dropped)(均保持入参排序序;dropped 供 debug 日志)"""
    kept: list[WbEntry] = [e for e in ordered if e.mode == "always"]
    triggers = [e for e in ordered if e.mode == "trigger"]
    # 保底:前 3 条 trigger 无视预算直接进
    kept += triggers[:TRIGGER_KEEP_MIN]
    rest = triggers[TRIGGER_KEEP_MIN:]
    used = sum(e.token_estimate for e in kept)
    for e in rest:
        if used + e.token_estimate > budget:
            continue   # 超预算:跳过该条,继续尝试更小的(排序序在前的优先,不提前 break)
        kept.append(e)
        used += e.token_estimate
    # 按身份 id 比较(条目内容可能同值,按值比较会误判)
    kept_ids = {e.id for e in kept}
    dropped = [e for e in ordered if e.id not in kept_ids]
    # 条数硬顶:always 优先占位,余量给 trigger(按排序序)
    if max_entries > 0 and len(kept) > max_entries:
        kept_always = [e for e in kept if e.mode == "always"]
        kept_trigger = [e for e in kept if e.mode != "always"]
        if len(kept_always) >= max_entries:
            kept = kept_always[:max_entries]
        else:
            kept = kept_always + kept_trigger[:max_entries - len(kept_always)]
        kept_ids = {e.id for e in kept}
        dropped = [e for e in ordered if e.id not in kept_ids]
    return kept, dropped


def render_sections(entries: list[WbEntry]) -> dict[str, str]:
    """渲染(docs/09 §2.5):每条一行 `- {content}`(不加标题防复读);按 position 分组,
    组内换行连接。返回 {position: 多行文本}(空组不出键;整体插入锚点时组间自然空行)"""
    sections: dict[str, list[str]] = {}
    for e in entries:
        sections.setdefault(e.position, []).append(f"- {e.content}")
    return {pos: "\n".join(lines) for pos, lines in sections.items()}


def select_for_injection(entries: list[WbEntry], texts: list[str], now_ms: int,
                         budget: int = 2000, max_entries: int = 12,
                         rng: random.Random | None = None) -> dict:
    """一站式注入选择(纯逻辑组合,worldbook_runtime 调):收集→过滤→排序→裁剪→渲染。
    返回 {"sections": {position: text}, "kept": [WbEntry], "dropped": [WbEntry],
          "tokens": kept token 合计, "hit_ids": [id](含被概率/冷却/裁剪刷掉的命中条目)}"""
    candidates = collect_candidates(entries, texts)
    hit_ids = [e.id for e in candidates]
    survived = filter_entries(candidates, now_ms, rng=rng)
    ordered = sort_entries(survived)
    kept, dropped = budget_trim(ordered, budget, max_entries=max_entries)
    return {
        "sections": render_sections(kept),
        "kept": kept,
        "dropped": dropped,
        "tokens": sum(e.token_estimate for e in kept),
        "hit_ids": hit_ids,
    }


def merge_stats(entry: WbEntry, *, hit: bool = False, injected: bool = False,
                now_ms: int = 0) -> None:
    """命中/注入记账(就地改,docs/09 §2.6):命中未注入只刷 last_hit_at;
    真实注入 hits+=1 + last_injected_at/last_hit_at 同刷"""
    now_ms = now_ms or int(time.time() * 1000)
    if hit:
        entry.last_hit_at = now_ms
    if injected:
        entry.hits += 1
        entry.last_injected_at = now_ms
        entry.last_hit_at = now_ms
