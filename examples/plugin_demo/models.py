"""Small fake chat model used to keep the prototype runnable offline.

In production this module would not exist in the agent core.  A real LLM plugin
would instead return an instance of ``ChatOpenAI``, ``ChatAnthropic``, or any
other LangChain ``BaseChatModel`` implementation.
"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class ScriptedToolCallModel(BaseChatModel):
    """Returns a fixed sequence of AIMessages and supports ``bind_tools``.

    The first message asks the agent to call the ``add`` tool; the second
    message provides the final answer.  This lets the example exercise the
    real LangChain agent loop, including the ToolNode, without requiring an
    API key.
    """

    responses: list[AIMessage]
    i: int = 0

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        response = self.responses[self.i]
        self.i = (self.i + 1) % len(self.responses)
        return ChatResult(generations=[ChatGeneration(message=response)])

    @property
    def _llm_type(self) -> str:
        return "scripted-tool-call-model"

    def bind_tools(self, tools, **kwargs):
        # ``create_agent`` calls bind_tools at runtime.  This fake model does not
        # need to change its behaviour, but it must accept the call.
        return self
