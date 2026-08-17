"""
插件清单(manifest)解析
从 plugin.yaml 读取插件元信息:name/version/author/description/entry/hooks/default_enabled/config_schema/requires
+ display_name(中文展示名)/category(中文分类),缺省回退。
钩子名合法集与 base.ALL_HOOKS 保持一致。

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 从 V1.0 移植 manifest 解析到 V2.0(零业务改动;供 M6 .star 兼容层加载纯插件用)
"""
from dataclasses import dataclass, field
from pathlib import Path

import yaml  # pyyaml:解析 plugin.yaml

# 合法钩子名(与 base.ALL_HOOKS 一致;此处单独列出避免与 base 互相导入)
VALID_HOOKS = {
    "on_message_in", "on_before_llm", "on_after_llm",
    "on_message_out", "on_tick", "on_delete",
}

# 分类缺省值(后端单一真源,前端无需再处理空值)
DEFAULT_CATEGORY = "未分类"


@dataclass
class HookEntry:
    """单个钩子订阅声明:name + priority(小先执行)"""
    name: str
    priority: int = 100


@dataclass
class PluginManifest:
    """插件清单数据模型"""
    name: str
    version: str = "0.0.0"
    author: str = ""
    description: str = ""
    entry: str = "plugin.py"
    hooks: list[HookEntry] = field(default_factory=list)
    default_enabled: bool = False
    config_schema: dict = field(default_factory=dict)   # 驱动面板表单 + 参数默认值
    requires: dict = field(default_factory=dict)        # 能力依赖,如 modality: [audio_out]
    display_name: str = ""   # 中文展示名,缺省回退 name
    category: str = ""       # 中文分类,缺省回退 DEFAULT_CATEGORY

    @property
    def hook_names(self) -> list[str]:
        return [h.name for h in self.hooks]


def parse_manifest(path: Path) -> PluginManifest:
    """从 plugin.yaml 解析清单。
    校验:name 非空、entry 非空、每个 hook 名在 VALID_HOOKS 内。违例抛 ValueError。"""
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"manifest 必须是字典: {path}")
    name = str(raw.get("name", "")).strip()
    if not name:
        raise ValueError(f"manifest 缺少 name: {path}")
    entry = str(raw.get("entry", "plugin.py")).strip() or "plugin.py"
    # hooks 支持两种写法:{name, priority} 字典 或 纯字符串钩子名(priority 默认 100)
    hooks: list[HookEntry] = []
    for h in (raw.get("hooks", []) or []):
        if isinstance(h, dict):
            hn = str(h.get("name", "")).strip()
            pri = int(h.get("priority", 100))
        else:
            hn = str(h).strip()
            pri = 100
        if hn not in VALID_HOOKS:
            raise ValueError(f"插件 {name} 声明了未知钩子: {hn}")
        hooks.append(HookEntry(name=hn, priority=pri))
    config_schema = raw.get("config_schema", {}) or {}
    requires = raw.get("requires", {}) or {}
    display_name = str(raw.get("display_name", "")).strip()
    category = str(raw.get("category", "")).strip()
    return PluginManifest(
        name=name,
        version=str(raw.get("version", "0.0.0")),
        author=str(raw.get("author", "")),
        description=str(raw.get("description", "")),
        entry=entry,
        hooks=hooks,
        default_enabled=bool(raw.get("default_enabled", False)),
        config_schema=config_schema if isinstance(config_schema, dict) else {},
        requires=requires if isinstance(requires, dict) else {},
        display_name=display_name,
        category=category,
    )
