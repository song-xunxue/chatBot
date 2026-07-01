"""
人设数据结构
PersonaCard 及其子结构(DynamicState/SpecialReply/ModelBinding/
Profile/Preferences/Relationship/DialogueExample),
统一人设的数据载体,供 store/renderer/importer 使用。

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 从 V1.0 移植 persona 数据结构到 V2.0(零业务改动;含 profile/preferences 等 V1.1 扩字段,
     反推快照 history/version 字段为 M3 评分反推预留)
"""
import time
from dataclasses import dataclass, field, asdict, fields


@dataclass
class DynamicState:
    """动态状态:心情/状态/精力(由 mood 服务更新)"""
    mood: str = ""          # 如 "温柔",自由文本(首版不强制枚举)
    status: str = ""        # 如 "在宅邸整理家务"
    energy: float = 0.8     # 0~1


@dataclass
class SpecialReply:
    """特殊回复:关键词触发固定回复(首版单关键词包含匹配)"""
    when_keyword: str = ""
    reply: str = ""
    weight: float = 1.0


@dataclass
class ModelBinding:
    """模型绑定:该人设使用的 LLM provider/model/参数。
    provider 空=继承全局 settings.chat_provider(避免旧默认 glm 锁死人设,GLM 限流时切不动)"""
    provider: str = ""
    model: str = ""
    params: dict = field(default_factory=dict)


@dataclass
class Profile:
    """人物画像:年龄/性别/职业/外貌/种族/说话风格/口头禅,全可选缺省空串"""
    age: str = ""           # str 容纳 "约20岁"/"不详" 等自由文本(非 int)
    gender: str = ""
    occupation: str = ""
    appearance: str = ""
    race: str = ""
    speech_style: str = ""  # 说话风格,如 "温柔慵懒、爱用叠词"
    catchphrase: str = ""   # 口头禅


@dataclass
class Preferences:
    """喜好与厌恶:字符串列表"""
    likes: list = field(default_factory=list)
    dislikes: list = field(default_factory=list)


@dataclass
class Relationship:
    """与用户的关系:关系 + 开场白"""
    relation: str = ""      # 如 "青梅竹马"/"主仆"
    greeting: str = ""      # 开场白(新会话由服务端下发,不经过 LLM;renderer 单独成段只渲染一次)


@dataclass
class DialogueExample:
    """示例对话单条:few-shot 注入 + 代人代答样本载体"""
    user: str = ""
    character: str = ""


def _filter_kwargs(cls, raw: dict) -> dict:
    """只保留 cls 声明的字段键,容忍未知键(兼容旧数据/导入)"""
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in raw.items() if k in names}


@dataclass
class PersonaCard:
    """人设卡片:完整人设数据"""
    schema_version: str = "1.1"                  # from_dict 读旧卡保留原值(纯审计)
    id: str = ""                                # persona_id,导入时取 prompts 首个 key 或生成
    name: str = ""
    language: str = "zh-CN"
    description: str = ""                        # 背景设定
    personality: str = ""                        # 性格
    scenario: str = ""                           # 场景示例
    creator_notes: str = ""                      # 核心人设指令
    avatar: str = ""                             # "static/avatar/<id>.jpg"
    images: list = field(default_factory=list)
    profile: Profile = field(default_factory=Profile)
    preferences: Preferences = field(default_factory=Preferences)
    relationship: Relationship = field(default_factory=Relationship)
    example_dialogue: list = field(default_factory=list)   # list[DialogueExample],few-shot + 代答样本载体
    dynamic_state: DynamicState = field(default_factory=DynamicState)
    special_replies: list = field(default_factory=list)
    model: ModelBinding = field(default_factory=ModelBinding)
    plugins: list = field(default_factory=list)
    version: int = 1                             # 乐观锁版本号(反推 CAS 铺路)
    history: list = field(default_factory=list)  # 反推回滚快照 list[dict],max 20
    created_ts: int = 0
    updated_ts: int = 0

    def __post_init__(self):
        now = int(time.time() * 1000)
        if not self.created_ts:
            self.created_ts = now
        if not self.updated_ts:
            self.updated_ts = now

    def to_dict(self) -> dict:
        """序列化为可 JSON 化的 dict(嵌套 dataclass 递归展开)"""
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> "PersonaCard":
        """从 dict 反序列化,容忍缺失字段与未知键(兼容旧数据/导入)"""
        raw = dict(raw or {})
        ds = DynamicState(**_filter_kwargs(DynamicState, raw.get("dynamic_state") or {}))
        srs = [SpecialReply(**_filter_kwargs(SpecialReply, sr))
               for sr in (raw.get("special_replies") or []) if isinstance(sr, dict)]
        mb = ModelBinding(**_filter_kwargs(ModelBinding, raw.get("model") or {}))
        prof = Profile(**_filter_kwargs(Profile, raw.get("profile") or {}))
        prefs = Preferences(**_filter_kwargs(Preferences, raw.get("preferences") or {}))
        rel = Relationship(**_filter_kwargs(Relationship, raw.get("relationship") or {}))
        dialogues = [DialogueExample(**_filter_kwargs(DialogueExample, d))
                     for d in (raw.get("example_dialogue") or []) if isinstance(d, dict)]
        kwargs = _filter_kwargs(cls, raw)
        # 嵌套对象已单独构造,从 kwargs 移除原始 dict/list 形态避免类型冲突
        for k in ("dynamic_state", "special_replies", "model",
                  "profile", "preferences", "relationship", "example_dialogue"):
            kwargs.pop(k, None)
        # history 是 list[dict](平铺快照),由 _filter_kwargs 保留直接透传,无需构造
        return cls(dynamic_state=ds, special_replies=srs, model=mb,
                   profile=prof, preferences=prefs, relationship=rel,
                   example_dialogue=dialogues, **kwargs)
