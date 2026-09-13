"""Localized UI strings for the CLI."""

from __future__ import annotations

import os

LOCALES = ("en", "zh")

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "intro": (
            "Type a message to start a conversation.\n"
            "/help shows commands · /exit leaves safely"
        ),
        "toolbar_hint": "/help for commands",
        "tokens": "{count} tokens",
        "cancelled": "Cancelled",
        "unknown_command": "Unknown command: /{name}. Type /help for available commands.",
        "error_prefix": "Error",
        "thinking": "thinking…",
        "tool_error": "error",
        "usage_io": "{in_tokens} in / {out_tokens} out",
        "help_exit": "Exit the interactive shell",
        "help_help": "Show available interactive commands",
        "help_unknown": "Unknown command: /{name}",
    },
    "zh": {
        "intro": "输入消息开始对话。\n/help 查看命令 · /exit 安全退出",
        "toolbar_hint": "/help 查看命令",
        "tokens": "{count} 令牌",
        "cancelled": "已取消",
        "unknown_command": "未知命令: /{name}。输入 /help 查看可用命令。",
        "error_prefix": "错误",
        "thinking": "思考中…",
        "tool_error": "错误",
        "usage_io": "输入 {in_tokens} / 输出 {out_tokens}",
        "help_exit": "退出交互式 shell",
        "help_help": "显示可用的交互命令",
        "help_unknown": "未知命令: /{name}",
    },
}


def tr(locale: str, key: str, **fmt: object) -> str:
    """Return the localized string for `key`, falling back to English."""
    table = STRINGS.get(locale, STRINGS["en"])
    template = table.get(key, STRINGS["en"].get(key, key))
    return template.format(**fmt) if fmt else template


def get_locale() -> str:
    """Resolve the UI locale from LANG_HARMESS_LOCALE (default "en")."""
    locale = os.environ.get("LANG_HARMESS_LOCALE", "en").lower()
    return locale if locale in LOCALES else "en"
