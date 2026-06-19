"""
LLM Provider 抽象基类
统一各家大模型（GLM/DeepSeek/硅基流动）的调用接口，屏蔽 API 差异。
M2.1 定义抽象契约：chat 一次性回复 + stream_chat 流式分片。

作者: 李文煜
日期: 2026-06-19

2026-06-19
变更说明：
  1. M2.1 创建 LLMProvider 抽象与 Message/Delta/LLMResponse 数据结构
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass
class Message:
    """OpenAI 风格对话消息：role(user/assistant/system) + content"""
    role: str       # "system" | "user" | "assistant"
    content: str


@dataclass
class Delta:
    """流式分片：本次增量文本（LLM 边产边推 WebSocket）"""
    text: str = ""


@dataclass
class LLMResponse:
    """一次性调用的完整回复"""
    text: str
    finish_reason: str = ""   # stop / length / content_filter 等


class LLMProvider(ABC):
    """LLM Provider 抽象基类：子类对接具体厂商 API（GLM/DeepSeek/硅基流动）"""

    name: str = ""   # provider 标识：glm / deepseek / siliconflow

    @abstractmethod
    async def chat(self, messages: list[Message], model: str = "", **opts) -> LLMResponse:
        """一次性调用：返回完整回复文本"""
        ...

    @abstractmethod
    async def stream_chat(self, messages: list[Message], model: str = "", **opts) -> AsyncIterator[Delta]:
        """流式调用：异步生成器逐 token 产出 Delta，供 WebSocket 实时推送"""
        ...
