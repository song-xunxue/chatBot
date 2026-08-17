"""
DeepSeek Provider —— OpenAI 兼容
DeepSeek 官方提供 OpenAI 兼容接口,base_url 为 https://api.deepseek.com。

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 从 V1.0 移植到 V2.0(零业务改动;默认模型 deepseek-chat)
"""
from llm.openai_compat import OpenAICompatProvider


class DeepSeekProvider(OpenAICompatProvider):
    name = "deepseek"
    base_url = "https://api.deepseek.com"
    default_model = "deepseek-chat"
