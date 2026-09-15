"""Identifier validation and memory keys shared across layers."""

from __future__ import annotations

import re

ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_RESERVED_IDS = frozenset({".", ".."})


def validate_id(value: str, *, field: str) -> str:
    """Validate an identifier used in thread keys, LDAP filters, and paths."""
    if not isinstance(value, str) or value in _RESERVED_IDS or not ID_PATTERN.match(value):
        raise ValueError(f"Invalid {field}: {value!r}")
    return value


def thread_key(user_id: str, session_id: str) -> str:
    """Build the LangGraph thread id isolating one user's session memory."""
    user = validate_id(user_id, field="user_id")
    session = validate_id(session_id, field="session_id")
    return f"{user}::{session}"
