"""
人设 JSON 导入兼容
兼容两种 persona_*.json 形态：
  - 嵌套形态：data.prompts.<任意key>.data.{name,description,...}（如 persona_雷姆.json）
  - 扁平形态：data.{name,description,...}（ST V2 完整卡）
对应 docs/09 §3.2。

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M3.1 创建 parse_persona_json/parse_persona_file，兼容嵌套/扁平两形态
"""
import json
import os
import time

from persona.models import PersonaCard


def parse_persona_json(raw: dict, persona_id: str = "") -> PersonaCard:
    """解析 persona_*.json dict 为 PersonaCard，兼容嵌套/扁平两形态"""
    data = raw.get("data", raw) if isinstance(raw, dict) else {}
    if not isinstance(data, dict):
        data = {}
    inner: dict = {}
    pid = persona_id
    prompts = data.get("prompts")
    if isinstance(prompts, dict) and prompts:
        # 嵌套形态：取首个 prompt key 作为 persona_id（容忍空格/撇号等任意 key 名）
        first_key = next(iter(prompts))
        inner = prompts[first_key].get("data", {}) or {}
        pid = pid or first_key
    else:
        # 扁平形态：字段直接在 data 下
        inner = data
    card = PersonaCard(
        id=pid or f"persona_{int(time.time() * 1000)}",
        name=inner.get("name", ""),
        description=inner.get("description", ""),
        personality=inner.get("personality", ""),
        scenario=inner.get("scenario", ""),
        creator_notes=inner.get("creator_notes", ""),
    )
    # avatar_path 跨设备不可移植：剥离路径只留文件名，标记需重新上传
    ap = inner.get("avatar_path", "")
    if ap:
        card.avatar = f"static/avatar/{card.id}/{os.path.basename(ap)}"
    return card


def parse_persona_file(path: str, persona_id: str = "") -> PersonaCard:
    """从文件读取并解析（强制 utf-8）"""
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return parse_persona_json(raw, persona_id)
