"""
本地 LLM Provider(OpenAI 兼容,2026-09-12 前置工作 A1)
指向本地/自建推理服务(Ollama / vLLM / LM Studio 等 OpenAI 兼容端点),
经 frp 隧道供云上容器调用(复用 GPT-SoVITS 同款链路:本地 4060 跑模型,
frpc 穿透 11434,容器内 host.docker.internal 访问)。

关键实现(踩坑复用):frp tcp 隧道对异步 httpx(httpcore)不兼容——
RemoteProtocolError: Server disconnected(与 modality/tts.GPTSoVitsProvider 同源),
故 chat/chat_with_tools 用同步 httpx.Client + asyncio.to_thread(不阻塞事件循环);
stream_chat 以非流式取全文后一次性 yield(QQ 场景本就累积完整回复再下发,无逐 token 需求)。

Qwen3 thinking 处理:Ollama 的 qwen3 默认输出 <think>...</think> 思考段,
出口统一剥除(_strip_think),并随 payload 附 think=False(新版 Ollama 支持,旧版忽略)。

作者: 李文煜
日期: 2026-09-12
"""
import asyncio
import re
from typing import AsyncIterator

import httpx

from llm.base import LLMProvider, Message, Delta, LLMResponse
from llm.openai_compat import OpenAICompatProvider
from core.config import settings

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_think(text: str) -> str:
    """剥除 Qwen3 思考段(<think>...</think>),未闭合容错只留正文"""
    if "</think>" in text:
        text = _THINK_RE.sub("", text)
        # 未闭合(截断):取 </think> 后内容已不可能,直接去 <think> 前缀
        if "<think>" in text:
            text = text.split("<think>", 1)[1] if "</think>" not in text else text
    return text.strip()


class LocalLLMProvider(OpenAICompatProvider):
    """本地 OpenAI 兼容推理服务(同步 httpx + to_thread 过 frp,详见模块注释)"""

    def __init__(self, api_key: str = ""):
        super().__init__(api_key or "ollama")   # Ollama 忽略鉴权,占位非空保 Bearer 头合法
        self.base_url = (settings.local_llm_api_base or "").rstrip("/")
        self.default_model = settings.local_llm_model or "qwen3:8b"

    def _payload(self, messages: list[dict], model: str, **opts) -> dict:
        # think=False 关思考(低延迟聊天);旧版 Ollama/vLLM 忽略未知字段
        return {"model": model or self.default_model, "messages": messages,
                "stream": False, "think": False, **opts}

    def _sync_chat(self, messages: list[dict], model: str, tools=None) -> dict:
        """同步调用(在 to_thread 里跑,frp 兼容);返回 choices[0].message"""
        payload = self._payload(messages, model)
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        with httpx.Client(timeout=180) as client:   # 本地 8B 生成较慢,放宽到 3min
            resp = client.post(self._chat_url(), headers=self._headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]

    async def chat(self, messages: list[Message], model: str = "", **opts) -> LLMResponse:
        """一次性调用:同步 httpx 经 to_thread 执行(frp 兼容),剥 <think> 段"""
        msgs = self._to_payload_messages(messages)
        choice = await asyncio.to_thread(self._sync_chat, msgs, model)
        return LLMResponse(text=_strip_think(choice["message"]["content"]),
                           finish_reason=choice.get("finish_reason", ""))

    async def chat_with_tools(self, messages: list[dict], model: str = "",
                              tools: list[dict] | None = None,
                              tool_choice: str = "auto") -> LLMResponse:
        """M5 tool-loop 用(messages 已是 dict 列表);同步线程执行 + tool_calls 解析"""
        choice = await asyncio.to_thread(self._sync_chat, messages, model, tools)
        msg = choice["message"]
        tool_calls = []
        for tc in msg.get("tool_calls", []) or []:
            fn = tc.get("function", {})
            tool_calls.append({
                "id": tc.get("id", ""),
                "name": fn.get("name", ""),
                "arguments": fn.get("arguments", "{}"),
            })
        return LLMResponse(text=_strip_think(msg.get("content", "") or ""),
                           finish_reason=choice.get("finish_reason", ""),
                           tool_calls=tool_calls)

    async def stream_chat(self, messages: list[Message], model: str = "", **opts) -> AsyncIterator[Delta]:
        """流式接口:frp 下不做真流式,非流式取全文后一次性 yield(调用方只消费完整文本)"""
        resp = await self.chat(messages, model, **opts)
        yield Delta(text=resp.text)
