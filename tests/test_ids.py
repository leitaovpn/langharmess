"""Unit tests for identifier validation and memory keys."""

from __future__ import annotations

import pytest

from langharmess_core.common.ids import thread_key, validate_id

VALID_IDS = [
    "local_user",
    "simple_agent",
    "agent-1",
    "user.name",
    "a" * 64,
    "0123456789",
    "UPPER_lower-9.9",
]


@pytest.mark.parametrize("value", VALID_IDS)
def test_validate_id_accepts_supported_characters(value: str) -> None:
    assert validate_id(value, field="agent_id") == value


@pytest.mark.parametrize(
    "value",
    [
        "",
        "a" * 65,
        "with space",
        "with/slash",
        "with:colon",
        "with(paren",
        "with)paren",
        "with=equals",
        "with*wildcard",
        "with\\backslash",
        "with\x00null",
        "..",
        ".",
        "中文",
    ],
)
def test_validate_id_rejects_unsupported_values(value: str) -> None:
    with pytest.raises(ValueError, match="agent_id"):
        validate_id(value, field="agent_id")


def test_validate_id_rejects_non_strings() -> None:
    with pytest.raises(ValueError, match="user_id"):
        validate_id(42, field="user_id")  # type: ignore[arg-type]


def test_validate_id_reports_field_name() -> None:
    with pytest.raises(ValueError, match="session_id"):
        validate_id("bad id", field="session_id")


def test_thread_key_combines_user_and_session() -> None:
    assert thread_key("local_user", "abc123") == "local_user::abc123"


def test_thread_key_rejects_invalid_ids() -> None:
    with pytest.raises(ValueError, match="user_id"):
        thread_key("bad user", "abc123")
    with pytest.raises(ValueError, match="session_id"):
        thread_key("local_user", "..")
