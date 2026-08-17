"""
OpenAI 兼容协议 Provider 基类
GLM / DeepSeek / 硅基流动均提供 OpenAI 兼容的 /chat/completions 接口,
本基类用 httpx 统一实现 chat(一次性) 与 stream_chat(流式 SSE),子类只需配置
base_url / api_key / default_model。

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 从 V1.0 移植到 V2.0(零业务改动;SSE 流式解析逻辑完全复用)
"""
import json
from typing import AsyncIterator

import httpx  # 异步 HTTP 客户端,支持流式 SSE 响应

from llm.base import LLMProvider, Message, Delta, LLMResponse


class OpenAICompatProvider(LLMProvider):
    """OpenAI 兼容协议基类:子类设置 base_url / api_key / default_model"""

    base_url: str = ""        # 各厂商 API 根地址(末尾不带 /)
    default_model: str = ""

    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    @property
    def _headers(self) -> dict:
        # OpenAI 兼容鉴权:Bearer token
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _chat_url(self) -> str:
        # 拼接 chat/completions 端点
        return f"{self.base_url}/chat/completions"

    @staticmethod
    def _to_payload_messages(messages: list[Message]) -> list[dict]:
        # 把 Message 列表转为 API 所需的 [{role, content}] 结构
        return [{"role": m.role, "content": m.content} for m in messages]

    async def chat(self, messages: list[Message], model: str = "", **opts) -> LLMResponse:
        """一次性调用:返回完整回复"""
        model = model or self.default_model
        payload = {"model": model, "messages": self._to_payload_messages(messages), "stream": False, **opts}
        async with httpx.AsyncClient(timeout=60) as client:
            # 同步等待完整 JSON 响应
            resp = await client.post(self._chat_url(), headers=self._headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            return LLMResponse(text=choice["message"]["content"], finish_reason=choice.get("finish_reason", ""))

    async def chat_with_tools(self, messages: list[dict], model: str = "",
                              tools: list[dict] | None = None,
                              tool_choice: str = "auto") -> LLMResponse:
        """M5 tool-loop 用:messages 为 list[dict](已含 system/user/assistant+tool_calls/tool 角色),
        直接作 payload messages(不经 _to_payload_messages)。传 tools 触发 function calling,
        解析响应 tool_calls。返回 LLMResponse(含 tool_calls)。"""
        payload = {"model": model or self.default_model, "messages": messages, "stream": False}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(self._chat_url(), headers=self._headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        choice = data["choices"][0]
        msg = choice["message"]
        tool_calls = []
        for tc in msg.get("tool_calls", []) or []:
            fn = tc.get("function", {})
            tool_calls.append({
                "id": tc.get("id", ""),
                "name": fn.get("name", ""),
                "arguments": fn.get("arguments", "{}"),   # str(JSON)
            })
        return LLMResponse(text=msg.get("content", "") or "",
                           finish_reason=choice.get("finish_reason", ""),
                           tool_calls=tool_calls)

    async def stream_chat(self, messages: list[Message], model: str = "", **opts) -> AsyncIterator[Delta]:
        """流式调用:异步生成器逐 token 产出 Delta(pipeline 累积为完整回复再下发 QQ)"""
        model = model or self.default_model
        payload = {"model": model, "messages": self._to_payload_messages(messages), "stream": True, **opts}
        async with httpx.AsyncClient(timeout=120) as client:
            # stream=True:响应体逐行读取(SSE 格式,每帧以 data: 开头)
            async with client.stream("POST", self._chat_url(), headers=self._headers, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    # SSE 协议:空行或非 data: 前缀的行跳过
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[len("data:"):].strip()
                    if data_str == "[DONE]":
                        # 流结束标志
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    # 取首个 choice 的增量内容
                    delta = chunk["choices"][0].get("delta", {})
                    text = delta.get("content") or ""
                    if text:
                        yield Delta(text=text)
