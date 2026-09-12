"""Contract tests for plugin service specifications and protocols."""

from __future__ import annotations

from langharmess.contracts import (
    LLMProvider,
    MiddlewareProvider,
    SystemPromptProvider,
    ToolProvider,
)
from langharmess.plugins.llm import LLMPlugin
from langharmess.plugins.middleware import MiddlewarePlugin
from langharmess.plugins.system_prompt import SystemPromptPlugin
from langharmess.plugins.tools import ToolPlugin


def test_concrete_plugins_conform_to_their_protocols() -> None:
    assert isinstance(LLMPlugin(), LLMProvider)
    assert isinstance(ToolPlugin(), ToolProvider)
    assert isinstance(MiddlewarePlugin(), MiddlewareProvider)
    assert isinstance(SystemPromptPlugin(), SystemPromptProvider)
