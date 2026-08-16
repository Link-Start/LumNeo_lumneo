# runtime/llm/port.py
# LLM Provider Port（运行时契约，§58）。
#
# Runtime 的 Agent / Client 只依赖此抽象，不感知具体 LLM SDK。
# 具体实现（OpenAI / Anthropic / Gemini / Local）放在 infrastructure/providers/，
# 由 Bootstrap 注入。这样切换模型供应商无需改动 Agent 核心逻辑。
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class LLMProvider(ABC):
    """LLM 供应商抽象。"""

    @abstractmethod
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
        """发起一次（流式）聊天补全，返回供应商原生的流式响应对象。

        返回的流由 runtime/llm/stream_parser 负责解析。
        """
        ...
