"""astrbot.api.provider 兼容(占位子集):LLMResponse / ProviderRequest / Provider。
V2.0 用自己的 llm provider 体系;此处仅提供 dataclass 占位,供 @on_llm_request/@on_llm_response
handler 接收参数时 import 不报错。深度 Provider API 不可用。

作者: 李文煜
日期: 2026-06-28
"""


class LLMResponse:
    """@on_llm_response handler 接收的响应(简化)"""
    def __init__(self, completion_text: str = "", **kw):
        self.completion_text = completion_text


class ProviderRequest:
    """@on_llm_request handler 接收的请求(可改 system_prompt)"""
    def __init__(self, system_prompt: str = "", **kw):
        self.system_prompt = system_prompt


class Provider:
    """占位(.star 插件 import 不报错;实际 provider 走 V2.0 llm 模块)"""
    pass
