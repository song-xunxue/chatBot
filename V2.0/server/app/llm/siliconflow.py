"""
硅基流动 Provider —— OpenAI 兼容(聚合型)
硅基流动聚合多个开源模型,提供 OpenAI 兼容接口;模型名形如 厂商/型号。

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 从 V1.0 移植到 V2.0(零业务改动;默认模型 deepseek-ai/DeepSeek-V3)
"""
from llm.openai_compat import OpenAICompatProvider


class SiliconFlowProvider(OpenAICompatProvider):
    name = "siliconflow"
    base_url = "https://api.siliconflow.cn/v1"
    default_model = "deepseek-ai/DeepSeek-V3"
