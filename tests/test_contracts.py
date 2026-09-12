"""Contract tests for plugin service specifications and protocols."""

from __future__ import annotations

from langharmess.contracts import (
    LLMProvider,
    MiddlewareProvider,
    SystemPromptProvider,
    ToolProvider,
)
from langharmess.plugins.loop.llm.llm import LLMPlugin
from langharmess.plugins.loop.middleware.template_middleware import (
    TemplateMiddlewarePlugin,
)
from langharmess.plugins.loop.system_prompt.template_system_prompt import (
    TemplateSystemPromptPlugin,
)
from langharmess.plugins.loop.tools.tools import ToolPlugin


def test_concrete_plugins_conform_to_their_protocols() -> None:
    assert isinstance(LLMPlugin(), LLMProvider)
    assert isinstance(ToolPlugin(), ToolProvider)
    assert isinstance(TemplateMiddlewarePlugin(), MiddlewareProvider)
    assert isinstance(TemplateSystemPromptPlugin(), SystemPromptProvider)
