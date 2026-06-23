"""
人设数据结构
PersonaCard 及其子结构（DynamicState/SpecialReply/ModelBinding），
统一人设的数据载体，供 store/renderer/importer/rest 使用。
对应 docs/03 §5 人设接口、docs/09 §3.1。

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M3.1 创建人设数据结构：PersonaCard + DynamicState/SpecialReply/ModelBinding
"""
import time
from dataclasses import dataclass, field, asdict, fields


@dataclass
class DynamicState:
    """动态状态：心情/状态/精力，由 mood_dynamic 插件更新（M4）"""
    mood: str = ""          # 如 "温柔"，自由文本（首版不强制枚举）
    status: str = ""        # 如 "在宅邸整理家务"
    energy: float = 0.8     # 0~1


@dataclass
class SpecialReply:
    """特殊回复：关键词触发固定回复（首版单关键词包含匹配）"""
    when_keyword: str = ""
    reply: str = ""
    weight: float = 1.0


@dataclass
class ModelBinding:
    """模型绑定：该人设使用的 LLM provider/model/参数"""
    provider: str = "glm"
    model: str = ""
    params: dict = field(default_factory=dict)


def _filter_kwargs(cls, raw: dict) -> dict:
    """只保留 cls 声明的字段键，容忍未知键（兼容旧数据/导入）"""
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in raw.items() if k in names}


@dataclass
class PersonaCard:
    """人设卡片：完整人设数据，对应 docs/03 §5 / docs/09 §3.1"""
    schema_version: str = "1.0"
    id: str = ""                              # persona_id，导入时取 prompts 首个 key 或生成
    name: str = ""
    language: str = "zh-CN"
    description: str = ""                     # 背景设定
    personality: str = ""                     # 性格
    scenario: str = ""                        # 场景示例
    creator_notes: str = ""                   # 核心人设指令
    avatar: str = ""                          # "static/avatar/<id>.jpg"
    images: list[str] = field(default_factory=list)
    dynamic_state: DynamicState = field(default_factory=DynamicState)
    special_replies: list[SpecialReply] = field(default_factory=list)
    model: ModelBinding = field(default_factory=ModelBinding)
    plugins: list[str] = field(default_factory=list)
    created_ts: int = 0
    updated_ts: int = 0

    def __post_init__(self):
        now = int(time.time() * 1000)
        if not self.created_ts:
            self.created_ts = now
        if not self.updated_ts:
            self.updated_ts = now

    def to_dict(self) -> dict:
        """序列化为可 JSON 化的 dict（嵌套 dataclass 递归展开）"""
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> "PersonaCard":
        """从 dict 反序列化，容忍缺失字段与未知键（兼容旧数据/导入）"""
        raw = dict(raw or {})
        ds = DynamicState(**_filter_kwargs(DynamicState, raw.get("dynamic_state") or {}))
        srs = [SpecialReply(**_filter_kwargs(SpecialReply, sr))
               for sr in (raw.get("special_replies") or []) if isinstance(sr, dict)]
        mb = ModelBinding(**_filter_kwargs(ModelBinding, raw.get("model") or {}))
        kwargs = _filter_kwargs(cls, raw)
        # 嵌套对象已单独构造，从 kwargs 移除原始 dict 形态避免类型冲突
        kwargs.pop("dynamic_state", None)
        kwargs.pop("special_replies", None)
        kwargs.pop("model", None)
        return cls(dynamic_state=ds, special_replies=srs, model=mb, **kwargs)
