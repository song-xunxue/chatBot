"""
manifest 解析单测：完整解析、缺 name、非法钩子、默认值

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M4.1 覆盖 parse_manifest 合法/非法/默认分支
"""
from pathlib import Path

import pytest

from plugins.manifest import parse_manifest


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "plugin.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_parse_full(tmp_path):
    p = _write(tmp_path,
        "name: tts\nversion: 0.2.0\nauthor: 李文煜\n"
        "description: x\nentry: plugin.py\n"
        "hooks:\n"
        "  - { name: on_after_llm, priority: 100 }\n"
        "  - on_message_out\n"                       # 简写字符串写法
        "default_enabled: true\n"
        "config_schema:\n  voice: { type: string, default: female }\n")
    mf = parse_manifest(p)
    assert mf.name == "tts"
    assert mf.version == "0.2.0"
    assert mf.author == "李文煜"
    assert mf.default_enabled is True
    assert [h.name for h in mf.hooks] == ["on_after_llm", "on_message_out"]
    assert mf.hooks[0].priority == 100
    assert mf.hooks[1].priority == 100     # 简写钩子 priority 默认 100
    assert mf.config_schema["voice"]["default"] == "female"


def test_missing_name_raises(tmp_path):
    with pytest.raises(ValueError):
        parse_manifest(_write(tmp_path, "version: 0.1.0\n"))


def test_invalid_hook_raises(tmp_path):
    with pytest.raises(ValueError):
        parse_manifest(_write(tmp_path, "name: bad\nhooks:\n  - on_unknown_hook\n"))


def test_defaults_when_minimal(tmp_path):
    mf = parse_manifest(_write(tmp_path, "name: minimal\n"))
    assert mf.entry == "plugin.py"
    assert mf.default_enabled is False
    assert mf.hooks == []
    assert mf.config_schema == {}


def test_non_dict_yaml_raises(tmp_path):
    with pytest.raises(ValueError):
        parse_manifest(_write(tmp_path, "- a\n- b\n"))   # 列表而非字典
