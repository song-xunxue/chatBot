"""
reverse_infer _llm_extract prompt 风格约束单测(2026-07-06 B-4):
验证提炼 prompt 含"禁括号动作描写"约束,防反推把舞台指示风格学进 speech_style/personality。
(LLM 真实提炼效果靠集成测;单测验证 prompt 被正确注入约束)

作者: 李文煜
日期: 2026-07-06
"""
from types import SimpleNamespace

from score.reverse_infer import _llm_extract


class _CaptureLLM:
    """mock LLM:捕获 _llm_extract 传入 prompt,返回空 JSON 对象"""

    def __init__(self):
        self.captured = ""

    async def chat(self, messages, model=""):
        self.captured = messages[0].content
        return SimpleNamespace(text="{}")


async def test_llm_extract_prompt_rejects_stage_direction_style():
    """B-4:_llm_extract prompt 须含风格提炼约束(禁括号动作/舞台指示/旁白)"""
    llm = _CaptureLLM()
    # 2026-07-07:_llm_extract 签名改为接收 dict 列表(含 source),按来源标注
    await _llm_extract(
        [{"text": "哈哈好啊", "source": "dialog"}, {"text": "嗯嗯没问题", "source": "dialog"}],
        [{"text": "（轻声笑了）你好", "source": "roleplay"}],
        llm,
    )
    p = llm.captured
    # 约束关键词
    assert "风格提炼约束" in p
    assert "括号动作" in p or "舞台指示" in p or "旁白" in p
    # 正负样本均喂入
    assert "哈哈好啊" in p
    assert "轻声笑了" in p


async def test_llm_extract_prompt_marks_sample_source():
    """2026-07-07:_llm_extract prompt 须按来源标注([真实对话]/[训练剧本]),供反推区分对待
    (真实对话权威,剧本参考)——修 score 队列 roleplay/live 共池无 source 区分的已存在污染"""
    llm = _CaptureLLM()
    await _llm_extract(
        [{"text": "真实对话回复", "source": "dialog"}],
        [{"text": "剧本偏离回复", "source": "roleplay"}],
        llm,
    )
    p = llm.captured
    assert "真实对话" in p
    assert "训练剧本" in p
    assert "真实对话回复" in p
    assert "剧本偏离回复" in p
