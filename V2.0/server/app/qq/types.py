"""
QQ 事件与凭证的数据类型(M1 用 @dataclass,避免与 QQ 原始 payload dict 双重建模)

作者: 李文煜
日期: 2026-06-25

2026-06-25
变更说明：
  1. M1 定义 C2C_MESSAGE_CREATE 事件解析结果 + access_token 缓存结构
"""
from dataclasses import dataclass


@dataclass
class C2CMessage:
    """用户私聊(C2C)消息事件解析结果(QQ 官方事件 payload.d 解析,字段来源 QQ 文档「事件」)"""
    openid: str       # 发送者 openid(取 d.author.user_openid),作本项目的 object_id
    content: str      # 文本内容(取 d.content)
    msg_id: str       # 平台方消息 id(取 d.id),被动回复 60 分钟窗口内必带
    timestamp: str    # 消息生产时间(取 d.timestamp,RFC3339 字符串)
    raw: dict         # 原始事件 d(调试用)
    attachments: list = None  # 媒体附件(QQ d.attachments;图片/语音等,每项 {content_type,url,...});默认 None


    def __post_init__(self):
        # attachments 默认空 list(dataclass 可变默认需工厂,此处用 None+post_init 兜底)
        if self.attachments is None:
            self.attachments = []


@dataclass
class AccessToken:
    """QQ access_token 缓存条目(存 Redis,expires_at 为绝对过期时间戳便于提前刷新判断)"""
    value: str        # access_token 值
    expires_at: float  # 绝对过期时间戳(秒)
