"""
DeepSeek Provider —— OpenAI 兼容
DeepSeek 官方提供 OpenAI 兼容接口，base_url 为 https://api.deepseek.com。

作者: 李文煜
日期: 2026-06-19

2026-06-19
变更说明：
  1. M2.1 创建 DeepSeek Provider，默认模型 deepseek-chat
"""
from llm.openai_compat import OpenAICompatProvider


class DeepSeekProvider(OpenAICompatProvider):
    name = "deepseek"
    base_url = "https://api.deepseek.com"
    default_model = "deepseek-chat"
