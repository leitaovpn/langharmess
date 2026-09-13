"""Tests for the CLI i18n helper module."""

from __future__ import annotations

import pytest

from langharmess_cli.i18n import LOCALES, STRINGS, get_locale, tr


def test_locales_are_english_and_chinese() -> None:
    assert LOCALES == ("en", "zh")


def test_string_tables_cover_the_same_keys() -> None:
    assert set(STRINGS["en"]) == set(STRINGS["zh"])


def test_tr_returns_english_and_chinese_values() -> None:
    assert tr("en", "toolbar_hint") == "/help for commands"
    assert tr("zh", "toolbar_hint") == "/help 查看命令"


def test_tr_falls_back_to_english_for_unknown_locale() -> None:
    assert tr("fr", "toolbar_hint") == "/help for commands"


def test_tr_returns_key_itself_for_unknown_key() -> None:
    assert tr("en", "missing_key") == "missing_key"


def test_tr_formats_placeholders() -> None:
    assert (
        tr("en", "unknown_command", name="nope")
        == "Unknown command: /nope. Type /help for available commands."
    )
    assert tr("zh", "tokens", count="1.2k") == "1.2k 令牌"


def test_get_locale_defaults_to_english(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LANG_HARMESS_LOCALE", raising=False)
    assert get_locale() == "en"


def test_get_locale_reads_valid_env_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANG_HARMESS_LOCALE", "zh")
    assert get_locale() == "zh"


def test_get_locale_normalizes_case(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANG_HARMESS_LOCALE", "ZH")
    assert get_locale() == "zh"


def test_get_locale_rejects_invalid_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANG_HARMESS_LOCALE", "fr")
    assert get_locale() == "en"
