"""
四级记忆数据结构
MemoryItem(长期)/ EpisodicEntry(情景摘要)/ CoreFact(核心)/
RecallResult / ForgetConfig / Layer / Category。

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 从 V1.0 移植四级记忆数据结构到 V2.0(零业务改动)
"""
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from llm.base import Message  # 仅类型注解用,避免运行时循环导入


class Layer(str, Enum):
    """四级记忆层级"""
    CORE = "core"
    WORKING = "working"
    EPISODIC = "episodic"
    LONG_TERM = "long_term"


class Category(str, Enum):
    """长期记忆类别"""
    FACT = "fact"
    PREFERENCE = "preference"
    RELATIONSHIP = "relationship"
    EVENT = "event"
    PERSONALITY = "personality"


@dataclass
class MemoryItem:
    """长期记忆条目(含 category/emotion/source)"""
    id: str                              # mid, uuid4
    content: str                         # 记忆文本
    category: Category = Category.FACT
    importance: float = 0.5              # 0~1, 写入时 LLM 评定
    emotion: float = 0.0                 # 0~1, 情感强度,影响衰减
    created_ts: int = 0                  # Unix 毫秒
    last_access_ts: int = 0
    access_count: int = 0
    forgotten: bool = False              # 软遗忘标记,可恢复
    source: str = "dialog"               # dialog/import/proxy/extract
    locked: bool = False                 # 锁定防遗忘(手动锁定,should_forget 跳过)

    def __post_init__(self):
        now = int(time.time() * 1000)
        if not self.created_ts:
            self.created_ts = now
        if not self.last_access_ts:
            self.last_access_ts = self.created_ts

    def to_dict(self) -> dict:
        d = asdict(self)
        # Enum 序列化为字符串
        d["category"] = self.category.value if isinstance(self.category, Category) else self.category
        return d

    @classmethod
    def from_dict(cls, raw: dict) -> "MemoryItem":
        raw = dict(raw or {})
        try:
            category = Category(raw.get("category", "fact"))
        except ValueError:
            category = Category.FACT
        return cls(
            id=raw.get("id", ""),
            content=raw.get("content", ""),
            category=category,
            importance=float(raw.get("importance", 0.5)),
            emotion=float(raw.get("emotion", 0.0)),
            created_ts=int(raw.get("created_ts", 0)),
            last_access_ts=int(raw.get("last_access_ts", 0)),
            access_count=int(raw.get("access_count", 0)),
            forgotten=bool(raw.get("forgotten", False)),
            source=raw.get("source", "dialog"),
            locked=bool(raw.get("locked", False)),
        )


@dataclass
class EpisodicEntry:
    """情景记忆摘要条目(ZSet member JSON)"""
    id: str
    summary: str                         # LLM 摘要
    span_start_ts: int
    span_end_ts: int
    created_ts: int = 0
    turn_range: tuple = (0, 0)           # 覆盖的 turn_index 范围

    def __post_init__(self):
        if not self.created_ts:
            self.created_ts = int(time.time() * 1000)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["turn_range"] = list(d["turn_range"])  # tuple → list 便于 JSON
        return d

    @classmethod
    def from_dict(cls, raw: dict) -> "EpisodicEntry":
        raw = dict(raw or {})
        tr = raw.get("turn_range", [0, 0])
        tr = tuple(tr) if isinstance(tr, (list, tuple)) else (0, 0)
        return cls(
            id=raw.get("id", ""),
            summary=raw.get("summary", ""),
            span_start_ts=int(raw.get("span_start_ts", 0)),
            span_end_ts=int(raw.get("span_end_ts", 0)),
            created_ts=int(raw.get("created_ts", 0)),
            turn_range=tr,
        )


@dataclass
class CoreFact:
    """核心记忆条目(常驻注入)"""
    key: str                             # 如 "user_name" / "persona_trait:温柔"
    content: str
    locked: bool = False                 # 锁定防遗忘

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> "CoreFact":
        raw = dict(raw or {})
        return cls(key=raw.get("key", ""), content=raw.get("content", ""),
                   locked=bool(raw.get("locked", False)))


@dataclass
class RecallResult:
    """coordinator.retrieve 返回:四层召回结果汇总"""
    core: list["CoreFact"] = field(default_factory=list)
    working: list["Message"] = field(default_factory=list)
    episodic: list["EpisodicEntry"] = field(default_factory=list)
    long_term: list["MemoryItem"] = field(default_factory=list)
    hit_mids: list[str] = field(default_factory=list)  # 被召回的 long_term mid,供更新访问统计


@dataclass
class ForgetConfig:
    """遗忘评分权重与阈值"""
    w_importance: float = 0.4
    w_recency: float = 0.3
    w_access: float = 0.15
    w_emotion: float = 0.15
    retain_threshold: float = 0.3        # 跌破则 forgotten=True
    decay_half_life_hours: float = 72.0  # recency_decay 半衰期
    cleanup_interval_turns: int = 50     # 物理清理周期
