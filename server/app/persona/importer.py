"""
人设 JSON 导入兼容
兼容两种 persona_*.json 形态：
  - 嵌套形态：data.prompts.<任意key>.data.{name,description,...}（如 persona_雷姆.json）
  - 扁平形态：data.{name,description,...}（ST V2 完整卡）
V1.1 M9：扩展支持 profile/preferences/relationship/example_dialogue 新字段，
  同时兼容 inner.profile.* 嵌套与 inner.age/gender/... 顶层扁平两种写法。
对应 docs/09 §3.2、docs/10 §4。

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M3.1 创建 parse_persona_json/parse_persona_file，兼容嵌套/扁平两形态

2026-06-24
变更说明：
  1. V1.1 M9 兼容新字段（嵌套/扁平两形态），缺新字段的旧 JSON 不报错且取缺省
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

    pid = pid or f"persona_{int(time.time() * 1000)}"
    payload = {
        "id": pid,
        "name": inner.get("name", ""),
        "description": inner.get("description", ""),
        "personality": inner.get("personality", ""),
        "scenario": inner.get("scenario", ""),
        "creator_notes": inner.get("creator_notes", ""),
    }
    # V1.1 M9 新字段：优先嵌套形态，回退顶层扁平形态
    if isinstance(inner.get("profile"), dict):
        payload["profile"] = inner["profile"]
    else:
        payload["profile"] = {k: inner[k] for k in
                              ("age", "gender", "occupation", "appearance", "race", "speech_style", "catchphrase")
                              if inner.get(k)}
    if isinstance(inner.get("preferences"), dict):
        payload["preferences"] = inner["preferences"]
    else:
        prefs = {}
        if inner.get("likes"):
            prefs["likes"] = inner["likes"]
        if inner.get("dislikes"):
            prefs["dislikes"] = inner["dislikes"]
        payload["preferences"] = prefs
    if isinstance(inner.get("relationship"), dict):
        payload["relationship"] = inner["relationship"]
    else:
        rel = {}
        if inner.get("relation"):
            rel["relation"] = inner["relation"]
        if inner.get("greeting"):
            rel["greeting"] = inner["greeting"]
        payload["relationship"] = rel
    if isinstance(inner.get("example_dialogue"), list):
        payload["example_dialogue"] = [d for d in inner["example_dialogue"] if isinstance(d, dict)]

    # avatar_path 跨设备不可移植：剥离路径只留文件名，标记需重新上传
    ap = inner.get("avatar_path", "")
    if ap:
        payload["avatar"] = f"static/avatar/{pid}/{os.path.basename(ap)}"
    return PersonaCard.from_dict(payload)


def parse_persona_file(path: str, persona_id: str = "") -> PersonaCard:
    """从文件读取并解析（强制 utf-8）"""
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return parse_persona_json(raw, persona_id)
