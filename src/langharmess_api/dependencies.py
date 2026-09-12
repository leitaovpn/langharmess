"""Shared FastAPI dependency sentinels."""

from __future__ import annotations

from typing import Any


def get_db_session() -> Any:
    """Return a database session configured by the DB plugin.

    The API server overrides this dependency when a DB provider is available.
    """
    raise RuntimeError("DB dependency is not configured")
