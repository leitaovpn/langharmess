"""Resolve CLI identity defaults from the API session index."""

from __future__ import annotations

import logging

import httpx

LOGGER = logging.getLogger("langharmess.cli")

DEFAULT_USER_ID = "local_user"
DEFAULT_AGENT_ID = "simple_agent"


def resolve_identity(
    base_url: str,
    token: str,
    user_id: str,
    *,
    agent_id: str | None = None,
    session_id: str | None = None,
    new_session: bool = False,
) -> tuple[str | None, str]:
    """Return the session and agent the interactive shell should start with."""
    latest_session_id, latest_agent_id = _latest_session(base_url, token, user_id)
    if session_id is None and not new_session:
        session_id = latest_session_id
    return session_id, agent_id or latest_agent_id or DEFAULT_AGENT_ID


def _latest_session(
    base_url: str, token: str, user_id: str
) -> tuple[str | None, str | None]:
    try:
        response = httpx.get(
            f"{base_url.rstrip('/')}/sessions",
            params={"user_id": user_id, "limit": 1},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        )
        response.raise_for_status()
        sessions = response.json().get("sessions") or []
    except (httpx.HTTPError, ValueError) as exc:
        LOGGER.warning("Could not load sessions for %s: %s", user_id, exc)
        return None, None
    if not sessions:
        return None, None
    latest = sessions[0]
    session_id = str(latest.get("session_id") or "") or None
    last_agent_id = str(latest.get("last_agent_id") or "") or None
    return session_id, last_agent_id
