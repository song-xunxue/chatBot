"""
GLM(智谱) Provider —— OpenAI 兼容
智谱开放平台提供 OpenAI 兼容接口,base_url 指向 /api/paas/v4。

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 从 V1.0 移植到 V2.0(零业务改动;默认模型 glm-4-flash 轻量省 token)
"""
from llm.openai_compat import OpenAICompatProvider


class GLMProvider(OpenAICompatProvider):
    name = "glm"
    base_url = "https://open.bigmodel.cn/api/paas/v4"
    default_model = "glm-4-flash"
