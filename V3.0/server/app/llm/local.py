"""
本地 LLM Provider(OpenAI 兼容,2026-09-12 前置工作 A1)
指向本地/自建推理服务(Ollama / vLLM / LM Studio 等 OpenAI 兼容端点),
经 frp 隧道供云上容器调用(复用 GPT-SoVITS 同款链路:本地 4060 跑模型,
frpc 穿透 11434,容器内 host.docker.internal 访问)。

关键实现(踩坑复用):frp tcp 隧道对异步 httpx(httpcore)不兼容——
RemoteProtocolError: Server disconnected(与 modality/tts.GPTSoVitsProvider 同源),
故 chat/chat_with_tools 用同步 httpx.Client + asyncio.to_thread(不阻塞事件循环);
stream_chat 以非流式取全文后一次性 yield(QQ 场景本就累积完整回复再下发,无逐 token 需求)。

Qwen3 thinking 处理(2026-10-25 修正):Ollama 的 OpenAI 兼容端点(/v1/chat/completions)
会忽略 payload 里的 "think" 字段——qwen3 默认思考,max_tokens 小时 token 全花在
<think> 段导致 content 为空。故 local_llm_disable_think 开(默认)时优先走 Ollama
原生 /api/chat(payload "think": false 真正生效);原生端点不可用(ConnectError/
HTTPStatusError,如后端是 vLLM)时回退 OpenAI 兼容路径 + 末条 user 消息注入
" /no_think" 软关思考。出口统一 _strip_think 剥除作兜底(所有路径保留)。

日期: 2026-09-12

2026-10-25
变更说明：
  1. 新增 Ollama 原生 /api/chat 分支真正关思考(think:false 生效),响应归一化成
     OpenAI choice 形状(顶层 message/done_reason → message.content/finish_reason;
     tool_calls 的 arguments 可能是 dict,json.dumps 成 str 与 OpenAI 路径一致)
  2. 原生分支失败回退 OpenAI 兼容路径,末条 user 消息注入 " /no_think"(无 user
     则注入 system 末尾);开关 local_llm_disable_think 关时保持原路径不变
"""
import asyncio
import json
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
        # 关思考开关(config.local_llm_disable_think):开=优先 Ollama 原生 /api/chat
        self.disable_think = settings.local_llm_disable_think

    def _payload(self, messages: list[dict], model: str, **opts) -> dict:
        # think=False 关思考(低延迟聊天);旧版 Ollama/vLLM 忽略未知字段
        return {"model": model or self.default_model, "messages": messages,
                "stream": False, "think": False, **opts}

    def _native_chat_url(self) -> str:
        """Ollama 原生端点:base_url 去掉末尾 /v1 拼 <root>/api/chat"""
        root = self.base_url[:-3] if self.base_url.endswith("/v1") else self.base_url
        return f"{root}/api/chat"

    @staticmethod
    def _inject_no_think(messages: list[dict]) -> list[dict]:
        """回退路径软关思考:末条 user 消息末尾注入 " /no_think"(Qwen3 软开关);
        无 user 消息则注入到末条 system 末尾。浅拷贝消息列表,不改调用方数据。"""
        msgs = [dict(m) for m in messages]
        for i in range(len(msgs) - 1, -1, -1):
            if msgs[i].get("role") == "user":
                msgs[i]["content"] = f"{msgs[i].get('content', '')} /no_think"
                return msgs
        for i in range(len(msgs) - 1, -1, -1):
            if msgs[i].get("role") == "system":
                msgs[i]["content"] = f"{msgs[i].get('content', '')} /no_think"
                return msgs
        return msgs   # 既无 user 也无 system:不注入(极端场景,交 _strip_think 兜底)

    def _sync_chat(self, messages: list[dict], model: str, tools=None) -> dict:
        """同步调用总入口(在 to_thread 里跑,frp 兼容);返回 choices[0].message 形状。
        关思考开:先试 Ollama 原生 /api_chat;不可用回退 OpenAI 兼容 + /no_think 注入。"""
        if self.disable_think:
            try:
                return self._sync_native_chat(messages, model, tools)
            except (httpx.ConnectError, httpx.HTTPStatusError):
                # 原生端点不可用(后端是 vLLM/LM Studio 等无 /api/chat):软关思考回退
                messages = self._inject_no_think(messages)
        return self._sync_openai_chat(messages, model, tools)

    def _sync_native_chat(self, messages: list[dict], model: str, tools=None) -> dict:
        """Ollama 原生 /api/chat 调用;响应(顶层 message/done_reason/eval_count)归一化成
        OpenAI choice 形状,chat/chat_with_tools 无感复用"""
        payload = {"model": model or self.default_model, "messages": messages,
                   "stream": False, "think": False}   # 原生端点 think:false 真正关思考
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        with httpx.Client(timeout=180) as client:   # 本地 8B 生成较慢,放宽到 3min
            resp = client.post(self._native_chat_url(), headers=self._headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        msg = data.get("message") or {}
        # 原生 tool_calls 的 arguments 可能是 dict(Ollama 行为),json.dumps 成
        # str(JSON) 与 OpenAI 路径一致(chat_with_tools 按 str 解析)
        tool_calls = []
        for tc in msg.get("tool_calls", []) or []:
            fn = tc.get("function", {})
            args = fn.get("arguments", "{}")
            if not isinstance(args, str):
                args = json.dumps(args, ensure_ascii=False)
            tool_calls.append({"id": tc.get("id", ""), "type": "function",
                               "function": {"name": fn.get("name", ""), "arguments": args}})
        return {"message": {"role": "assistant",
                            "content": msg.get("content", "") or "",
                            **({"tool_calls": tool_calls} if tool_calls else {})},
                "finish_reason": data.get("done_reason", "stop")}

    def _sync_openai_chat(self, messages: list[dict], model: str, tools=None) -> dict:
        """OpenAI 兼容 /chat/completions 调用(原路径;关思考关时唯一路径)"""
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
