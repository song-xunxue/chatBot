"""
硅基流动 Provider —— OpenAI 兼容（聚合型）
硅基流动聚合多个开源模型，提供 OpenAI 兼容接口；模型名形如 厂商/型号。

作者: 李文煜
日期: 2026-06-19

2026-06-19
变更说明：
  1. M2.1 创建硅基流动 Provider，默认模型 deepseek-ai/DeepSeek-V3
"""
from llm.openai_compat import OpenAICompatProvider


class SiliconFlowProvider(OpenAICompatProvider):
    name = "siliconflow"
    base_url = "https://api.siliconflow.cn/v1"
    default_model = "deepseek-ai/DeepSeek-V3"
