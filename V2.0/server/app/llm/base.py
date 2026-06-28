"""
LLM Provider 抽象基类
统一各家大模型(GLM/DeepSeek/硅基流动)的调用接口,屏蔽 API 差异。
定义抽象契约:chat 一次性回复 + stream_chat 流式分片。

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 从 V1.0 移植 llm 模块到 V2.0(零业务改动;Message 保持 role+content:str,多模态留 M6)
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class Message:
    """OpenAI 风格对话消息:role(user/assistant/system) + content"""
    role: str       # "system" | "user" | "assistant"
    content: str


@dataclass
class Delta:
    """流式分片:本次增量文本(LLM 边产边推,pipeline 累积为完整回复)"""
    text: str = ""


@dataclass
class LLMResponse:
    """一次性调用的完整回复"""
    text: str
    finish_reason: str = ""   # stop / length / content_filter / tool_calls 等
    tool_calls: list = field(default_factory=list)   # M5:[{id,name,arguments(str JSON)}],function calling


class LLMProvider(ABC):
    """LLM Provider 抽象基类:子类对接具体厂商 API(GLM/DeepSeek/硅基流动)"""

    name: str = ""   # provider 标识:glm / deepseek / siliconflow

    @abstractmethod
    async def chat(self, messages: list[Message], model: str = "", **opts) -> LLMResponse:
        """一次性调用:返回完整回复文本"""
        ...

    @abstractmethod
    async def stream_chat(self, messages: list[Message], model: str = "", **opts) -> AsyncIterator[Delta]:
        """流式调用:异步生成器逐 token 产出 Delta"""
        ...
