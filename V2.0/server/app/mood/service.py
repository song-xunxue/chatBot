"""
心情系统服务
mood∈[0,1](0.5 中性)动态维护 + 可配置心情种类表(档位 CRUD)+ 离散档位评分补偿。
从 V1.0 mood_dynamic 插件融入架构,对应 docs/03 §3(种类表)/§4(mood 动态)/§5(评分补偿)。

Redis 键:
  mychat:mood:{oid}          String  当前 mood 值(沿用 V1.0)
  mychat:mood:oids           Set     有 mood 记录的 oid 集合(衰减遍历用)
  mychat:mood:kinds          ZSet    档位索引(score=sort, member=key)
  mychat:mood:kind:{key}     Hash    单档位定义

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 新建 mood service:mood 读写/apply_emotion(复用 V1.0 词表)/档位 CRUD(含范围冲突校验)/
     lookup_kind/compute_mood_bias(M3 评分调)/默认 5 档 seed/list_mood_objects

2026-06-30
变更说明：
  1. M7 新增全局参数 get_params/set_params(Redis Hash,apply_emotion/decay 改读 Redis 回退 settings)+
     mood 历史曲线(set_mood 写 + get_history_curve,面板实时监控页)
"""
import json
import random
import time

from redis.asyncio import Redis

from core.config import settings

# mood 值键 + oids 索引 + 档位键
_K_MOOD = "mychat:mood:{oid}"
_K_OIDS = "mychat:mood:oids"
_K_KINDS = "mychat:mood:kinds"
_K_KIND = "mychat:mood:kind:{key}"
_K_PARAMS = "mychat:mood:params"            # 全局参数 Hash(M7 面板可写,apply_emotion/decay 读)
_K_HISTORY = "mychat:mood:{oid}:history"    # mood 历史曲线 List(LPUSH 新值在前,LTRIM 保留近 N 条)


def _now_ms() -> int:
    """当前毫秒时间戳"""
    return int(time.time() * 1000)


# 全局参数字段(名 → 取值转换;均属 [0,1] 范围,缺失时回退 settings 同名字段)
_PARAM_FIELDS = {
    "mood_step": float,
    "mood_decay": float,
    "mood_neutral": float,
    "mood_kaomoji_prob": float,
}

# 情感关键词表(复用 V1.0 mood_dynamic,零依赖启发式;M4 可换 LLM 情感分析)
_POSITIVE = ["开心", "高兴", "喜欢", "好棒", "谢谢", "想你", "爱你", "哈哈", "嘿嘿", "😊", "😄", "❤"]
_NEGATIVE = ["难过", "伤心", "讨厌", "好烦", "好累", "不开心", "对不起", "想哭", "😢", "😡", "焦虑"]

# 默认 5 档(docs/03 §3.2,复用 V1.0 颜文字;边界与 V1.0 _label 阈值 0.7/0.55/0.45/0.3 对齐)
_DEFAULT_KINDS = [
    {"key": "happy", "label": "开心", "mood_lo": 0.70, "mood_hi": 1.00,
     "kaomoji": "◍˃ᵕ˂◍", "score_bias": 6, "bias_noise": 3,
     "prompt_hint": "语气轻快热情,多用感叹和颜文字", "color": "#FFD666", "sort": 1},
    {"key": "pleased", "label": "愉悦", "mood_lo": 0.55, "mood_hi": 0.70,
     "kaomoji": "˗ˋˏ♡ˎˊ˗", "score_bias": 3, "bias_noise": 3,
     "prompt_hint": "语气温和友好,带点小开心", "color": "#FFB3C7", "sort": 2},
    {"key": "calm", "label": "平静", "mood_lo": 0.45, "mood_hi": 0.55,
     "kaomoji": "◌", "score_bias": 0, "bias_noise": 3,
     "prompt_hint": "语气平稳自然,不特别起伏", "color": "#C8C8C8", "sort": 3},
    {"key": "down", "label": "低落", "mood_lo": 0.30, "mood_hi": 0.45,
     "kaomoji": "˚‧º·(˚˃̣̣̥᷄⌓˂̣̣̥᷅)‧º·˚", "score_bias": -3, "bias_noise": 3,
     "prompt_hint": "语气低沉,话变少,略带消极", "color": "#9DB2C8", "sort": 4},
    {"key": "sad", "label": "难过", "mood_lo": 0.00, "mood_hi": 0.30,
     "kaomoji": "╥﹏╥", "score_bias": -6, "bias_noise": 3,
     "prompt_hint": "语气伤心,可能不想说话或欲言又止", "color": "#7A8FB5", "sort": 5},
]

# 档位 Hash 字段(Redis 存 str,读取转类型)
_KIND_FLOAT_FIELDS = ("mood_lo", "mood_hi", "bias_noise")
_KIND_INT_FIELDS = ("score_bias", "sort")


def _kind_to_hash(kind: dict) -> dict:
    """档位 dict → Redis Hash 的 str 值映射"""
    return {k: str(v) for k, v in kind.items()}


def _kind_to_dict(raw: dict) -> dict:
    """Redis Hash → 档位 dict(数值字段转 float/int)"""
    if not raw:
        return {}
    out = {
        "key": raw.get("key", ""),
        "label": raw.get("label", ""),
        "kaomoji": raw.get("kaomoji", ""),
        "prompt_hint": raw.get("prompt_hint", ""),
        "color": raw.get("color", ""),
    }
    for f in _KIND_FLOAT_FIELDS:
        try:
            out[f] = float(raw.get(f, 0))
        except (TypeError, ValueError):
            out[f] = 0.0
    for f in _KIND_INT_FIELDS:
        try:
            out[f] = int(float(raw.get(f, 0)))
        except (TypeError, ValueError):
            out[f] = 0
    return out


def _validate_coverage(kinds: list[dict]) -> None:
    """校验档位区间不重叠且覆盖 [0,1](docs/03 §3.3)。违例抛 ValueError。
    区间约定:左闭右开 [mood_lo, mood_hi);最高档 mood_hi=1.0 含端点(mood=1.0 命中)。"""
    if not kinds:
        raise ValueError("至少需要一个档位")
    intervals = sorted((float(k["mood_lo"]), float(k["mood_hi"])) for k in kinds)
    if intervals[0][0] > 1e-9:
        raise ValueError("档位未覆盖 mood=0")
    if intervals[-1][1] < 1.0 - 1e-9:
        raise ValueError("档位未覆盖 mood=1")
    prev_hi = 0.0
    for lo, hi in intervals:
        if lo >= hi:
            raise ValueError(f"档位区间非法: [{lo}, {hi})")
        if lo < prev_hi - 1e-9:
            raise ValueError(f"档位区间重叠: [{lo}, {hi}) 与前一档")
        if lo > prev_hi + 1e-9:
            raise ValueError(f"档位之间存在空隙: {prev_hi} ~ {lo}")
        prev_hi = hi


# ================ mood 值读写 ================

async def get_mood(redis: Redis, object_id: str) -> float:
    """取 mood 值;未设置返回中性 0.5"""
    v = await redis.get(_K_MOOD.format(oid=object_id))
    try:
        return float(v) if v is not None else 0.5
    except (TypeError, ValueError):
        return 0.5


async def set_mood(redis: Redis, object_id: str, mood: float) -> None:
    """写 mood 值(clamp [0,1],round 3 位);登记 oid 到 oids 集合(衰减遍历用);
    M7 同时写历史曲线(LPUSH + LTRIM 保留近 mood_history_keep 条)。"""
    mood = max(0.0, min(1.0, mood))
    mood = round(mood, 3)
    hist_key = _K_HISTORY.format(oid=object_id)
    pipe = redis.pipeline()
    pipe.set(_K_MOOD.format(oid=object_id), str(mood))
    pipe.sadd(_K_OIDS, object_id)
    pipe.lpush(hist_key, json.dumps({"ts": _now_ms(), "mood": mood}, ensure_ascii=False))
    pipe.ltrim(hist_key, 0, settings.mood_history_keep - 1)
    await pipe.execute()


async def apply_emotion(redis: Redis, object_id: str, text: str, *, step: float | None = None) -> float:
    """按文本关键词情感更新 mood(正向词↑step / 负向词↓step,可叠加),返回更新后 mood。
    step 默认读全局参数(Redis mood:params,回退 settings.mood_step)。复用 V1.0 正/负向词表(docs/03 §4.1)。"""
    if step is None:
        step = (await get_params(redis))["mood_step"]
    mood = await get_mood(redis, object_id)
    delta = 0.0
    if any(w in text for w in _POSITIVE):
        delta += step
    if any(w in text for w in _NEGATIVE):
        delta -= step
    if delta != 0.0:
        mood = max(0.0, min(1.0, mood + delta))
        await set_mood(redis, object_id, mood)
    return mood


async def list_mood_objects(redis: Redis) -> list[str]:
    """列出所有有 mood 记录的 oid(供衰减遍历)"""
    return sorted(await redis.smembers(_K_OIDS))


# ================ 档位/种类表 CRUD(docs/03 §3/§6)================

async def list_kinds(redis: Redis) -> list[dict]:
    """列全部档位(按 sort 升序)"""
    keys = await redis.zrange(_K_KINDS, 0, -1)   # ZSet 按 score(=sort)升序
    if not keys:
        return []
    pipe = redis.pipeline()
    for k in keys:
        pipe.hgetall(_K_KIND.format(key=k))
    raws = await pipe.execute()
    return [_kind_to_dict(r) for r in raws if r]


async def get_kind(redis: Redis, key: str) -> dict | None:
    """取单档位;不存在返回 None"""
    raw = await redis.hgetall(_K_KIND.format(key=key))
    return _kind_to_dict(raw) if raw else None


async def upsert_kind(redis: Redis, kind: dict) -> None:
    """新增/编辑档位(校验范围冲突,失败抛 ValueError)。
    必填字段:key/label/mood_lo/mood_hi/score_bias/bias_noise/prompt_hint/color/sort"""
    key = kind.get("key", "")
    if not key:
        raise ValueError("档位 key 不能为空")
    existing = await list_kinds(redis)
    merged = [k for k in existing if k["key"] != key] + [_kind_to_dict({**_kind_to_hash(kind)})]
    _validate_coverage(merged)
    pipe = redis.pipeline()
    pipe.hset(_K_KIND.format(key=key), mapping=_kind_to_hash(kind))
    pipe.zadd(_K_KINDS, {key: int(float(kind.get("sort", 0)))})
    await pipe.execute()


async def delete_kind(redis: Redis, key: str) -> None:
    """删档位(校验删后仍覆盖 [0,1] 且至少留一档,否则拒绝)"""
    existing = await list_kinds(redis)
    if len(existing) <= 1:
        raise ValueError("至少保留一个档位")
    merged = [k for k in existing if k["key"] != key]
    _validate_coverage(merged)
    pipe = redis.pipeline()
    pipe.delete(_K_KIND.format(key=key))
    pipe.zrem(_K_KINDS, key)
    await pipe.execute()


async def seed_default_kinds(redis: Redis) -> None:
    """启动时若种表为空,写入默认 5 档(docs/03 §3.2)"""
    if await redis.zcard(_K_KINDS) > 0:
        return
    _validate_coverage(_DEFAULT_KINDS)   # 默认档已覆盖 [0,1],校验兜底
    pipe = redis.pipeline()
    for k in _DEFAULT_KINDS:
        pipe.hset(_K_KIND.format(key=k["key"]), mapping=_kind_to_hash(k))
        pipe.zadd(_K_KINDS, {k["key"]: int(k["sort"])})
    await pipe.execute()


# ================ 档位查询 + 评分补偿(docs/03 §5,M3 调)================

def lookup_kind(mood: float, kinds: list[dict]) -> dict | None:
    """按 mood 值查所属档位(左闭右开 [mood_lo, mood_hi);最高档 mood=1.0 含端点)。
    返回 None 表示无匹配(种表未覆盖该 mood)。"""
    for k in sorted(kinds, key=lambda x: x.get("sort", 0)):
        lo = float(k.get("mood_lo", 0))
        hi = float(k.get("mood_hi", 1))
        if lo <= mood < hi:
            return k
    # mood 恰为 1.0(最高档上界)
    for k in sorted(kinds, key=lambda x: x.get("sort", 0)):
        hi = float(k.get("mood_hi", 1))
        if hi >= 1.0 and abs(mood - hi) < 1e-9:
            return k
    return None


def compute_mood_bias(mood: float, kinds: list[dict]) -> float:
    """评分补偿:档位.score_bias + uniform(-noise, noise)。
    噪声让相邻评分不完全可预测,更拟人(docs/03 §5)。无匹配档位返回 0。"""
    kind = lookup_kind(mood, kinds)
    if not kind:
        return 0.0
    bias = float(kind.get("score_bias", 0))
    noise = float(kind.get("bias_noise", 0))
    return bias + random.uniform(-noise, noise)


# ================ 全局参数 + 历史曲线(M7 面板用)================

async def get_params(redis: Redis) -> dict:
    """取全局参数(Redis Hash);缺失/非法字段回退 settings 同名字段,保证未配置时行为不变。
    返回 {mood_step, mood_decay, mood_neutral, mood_kaomoji_prob}。"""
    raw = await redis.hgetall(_K_PARAMS)
    out = {}
    for name, cast in _PARAM_FIELDS.items():
        v = raw.get(name, "")
        try:
            out[name] = cast(v) if v not in ("", None) else cast(getattr(settings, name))
        except (TypeError, ValueError):
            out[name] = cast(getattr(settings, name))
    return out


async def set_params(redis: Redis, params: dict) -> dict:
    """改全局参数(Redis Hash)。所有参数均须在 [0,1],违例抛 ValueError。返回回读结果。"""
    mapping = {}
    for name in _PARAM_FIELDS:
        if name not in params:
            continue
        try:
            v = float(params[name])
        except (TypeError, ValueError):
            raise ValueError(f"参数 {name} 必须是数值")
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"参数 {name} 须在 [0,1]")
        mapping[name] = str(v)
    if mapping:
        await redis.hset(_K_PARAMS, mapping=mapping)
    return await get_params(redis)


async def get_history_curve(redis: Redis, object_id: str, *, limit: int = 100) -> list[dict]:
    """mood 历史曲线(近 limit 点,旧→新正序),供面板实时监控页。返回 [{ts, mood}]。
    limit 上限 mood_history_keep(LPUSH+LTRIM 只保留这么多)。"""
    limit = min(limit, settings.mood_history_keep)
    raw = await redis.lrange(_K_HISTORY.format(oid=object_id), 0, limit - 1)   # LPUSH:新在前
    out = []
    for x in raw:
        try:
            d = json.loads(x)
            if isinstance(d, dict):
                out.append(d)
        except (json.JSONDecodeError, TypeError):
            pass
    out.reverse()   # 反转成旧→新正序(曲线左→右)
    return out
