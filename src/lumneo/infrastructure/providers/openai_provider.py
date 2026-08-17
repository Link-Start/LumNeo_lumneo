# infrastructure/providers/openai_provider.py
# OpenAI Provider Adapter（§37 / §58）。
#
# LLMProvider 的 OpenAI 实现。封装 AsyncOpenAI 客户端与请求参数构造，
# 把“具体 SDK 散落在 Agent 代码里”收敛到基础设施层。
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from lumneo.runtime.llm.port import LLMProvider


class OpenAIProvider(LLMProvider):
    """基于 OpenAI 兼容 API 的 LLM 供应商适配器。"""

    def __init__(
        self,
        model_type: str,
        model_name: str,
        api_key: str = "",
        base_url: Optional[str] = None,
        thinking: str = "enabled",
        reasoning_effort: str = "high",
    ):
        self.model_type = model_type
        self.model_name = model_name
        self.thinking = thinking
        self.reasoning_effort = reasoning_effort if thinking == "enabled" else None
        self.client = AsyncOpenAI(api_key=api_key or "none", base_url=base_url)

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        tool_choice: str = "auto",
        temperature: float = 1.0,
        top_p: float = 0.95,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
        top_k: int = 20,
        force_final: bool = False,
        **kwargs,
    ) -> Any:
        """发起流式聊天请求，返回异步流式响应对象。"""
        extra_body = {
            "top_k": top_k,
            "chat_template_kwargs": {},
            "thinking": {"type": self.thinking},
        }
        if self.thinking == "enabled":
            extra_body.update({
                "enable_thinking": True,
                "preserve_thinking": True,
                "chat_template_kwargs": {"enable_thinking": True, "preserve_thinking": True},
            })
        elif self.thinking == "disabled":
            extra_body.update({
                "enable_thinking": False,
                "preserve_thinking": False,
                "chat_template_kwargs": {"enable_thinking": False, "preserve_thinking": False},
            })

        request_params = {
            "model": self.model_name,
            "messages": messages,
            "stream": True,
            "reasoning_effort": self.reasoning_effort,
            "temperature": temperature,
            "top_p": top_p,
            "frequency_penalty": frequency_penalty,
            "presence_penalty": presence_penalty,
            "stream_options": {"include_usage": True},
            "extra_body": extra_body,
        }
        if tools and not force_final:
            request_params["tools"] = tools
            request_params["tool_choice"] = tool_choice

        return await self.client.chat.completions.create(**request_params)
