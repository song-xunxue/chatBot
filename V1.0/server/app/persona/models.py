"""
人设数据结构
PersonaCard 及其子结构（DynamicState/SpecialReply/ModelBinding/
Profile/Preferences/Relationship/DialogueExample），
统一人设的数据载体，供 store/renderer/importer/rest 使用。
对应 docs/03 §5 人设接口、docs/09 §3.1、docs/10 §4（V1.1 M9 扩字段）。

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M3.1 创建人设数据结构：PersonaCard + DynamicState/SpecialReply/ModelBinding

2026-06-24
变更说明：
  1. V1.1 M9 扩展人设字段：新增 Profile/Preferences/Relationship/DialogueExample
     四组嵌套可选字段（年龄/性别/职业/外貌/种族/说话风格/口头禅/喜恶/关系/开场白/示例对话，全缺省可空）
  2. 新增 version（乐观锁版本号，CAS 铺路）/ history（反推回滚快照）字段
  3. schema_version 默认升 1.1（旧 1.0 卡 from_dict 仍兼容，版本号纯审计不强制升级）
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


@dataclass
class Profile:
    """人物画像（V1.1 M9）：年龄/性别/职业/外貌/种族/说话风格/口头禅，全可选缺省空串"""
    age: str = ""           # str 容纳 "约20岁"/"不详" 等自由文本（非 int）
    gender: str = ""
    occupation: str = ""
    appearance: str = ""
    race: str = ""
    speech_style: str = ""  # 说话风格，如 "温柔慵懒、爱用叠词"
    catchphrase: str = ""   # 口头禅


@dataclass
class Preferences:
    """喜好与厌恶（V1.1 M9）：字符串列表"""
    likes: list = field(default_factory=list)
    dislikes: list = field(default_factory=list)


@dataclass
class Relationship:
    """与用户的关系（V1.1 M9）：关系 + 开场白"""
    relation: str = ""      # 如 "青梅竹马"/"主仆"
    greeting: str = ""      # 开场白（新会话由服务端下发，不经过 LLM；renderer 单独成段只渲染一次）


@dataclass
class DialogueExample:
    """示例对话单条（V1.1 M9）：few-shot 注入 + 代人代答样本载体"""
    user: str = ""
    character: str = ""


def _filter_kwargs(cls, raw: dict) -> dict:
    """只保留 cls 声明的字段键，容忍未知键（兼容旧数据/导入）"""
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in raw.items() if k in names}


@dataclass
class PersonaCard:
    """人设卡片：完整人设数据，对应 docs/03 §5 / docs/09 §3.1 / docs/10 §4"""
    schema_version: str = "1.1"                  # V1.1 升 1.1；from_dict 读旧卡保留原值（纯审计）
    id: str = ""                                # persona_id，导入时取 prompts 首个 key 或生成
    name: str = ""
    language: str = "zh-CN"
    description: str = ""                        # 背景设定
    personality: str = ""                        # 性格
    scenario: str = ""                           # 场景示例
    creator_notes: str = ""                      # 核心人设指令
    avatar: str = ""                             # "static/avatar/<id>.jpg"
    images: list = field(default_factory=list)
    # V1.1 M9 新增四组嵌套可选字段（全缺省可空，旧卡自动补缺省）
    profile: Profile = field(default_factory=Profile)
    preferences: Preferences = field(default_factory=Preferences)
    relationship: Relationship = field(default_factory=Relationship)
    example_dialogue: list = field(default_factory=list)   # list[DialogueExample]，few-shot + 代答样本载体
    dynamic_state: DynamicState = field(default_factory=DynamicState)
    special_replies: list = field(default_factory=list)
    model: ModelBinding = field(default_factory=ModelBinding)
    plugins: list = field(default_factory=list)
    version: int = 1                             # V1.1 M9 乐观锁版本号（M12 CAS 铺路）
    history: list = field(default_factory=list)  # V1.1 M12 反推回滚快照 list[dict]，max 20
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
        # V1.1 M9 四组嵌套字段
        prof = Profile(**_filter_kwargs(Profile, raw.get("profile") or {}))
        prefs = Preferences(**_filter_kwargs(Preferences, raw.get("preferences") or {}))
        rel = Relationship(**_filter_kwargs(Relationship, raw.get("relationship") or {}))
        dialogues = [DialogueExample(**_filter_kwargs(DialogueExample, d))
                     for d in (raw.get("example_dialogue") or []) if isinstance(d, dict)]
        kwargs = _filter_kwargs(cls, raw)
        # 嵌套对象已单独构造，从 kwargs 移除原始 dict/list 形态避免类型冲突
        for k in ("dynamic_state", "special_replies", "model",
                  "profile", "preferences", "relationship", "example_dialogue"):
            kwargs.pop(k, None)
        # history 是 list[dict]（平铺快照），由 _filter_kwargs 保留直接透传，无需构造
        return cls(dynamic_state=ds, special_replies=srs, model=mb,
                   profile=prof, preferences=prefs, relationship=rel,
                   example_dialogue=dialogues, **kwargs)
