"""Runtime validation of service objects against their Protocol contracts."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

LOGGER = logging.getLogger("langharmess.contract")

SPECIFICATION_FIELD = "__SPECIFICATION__"

CONTRACTS: dict[str, type[Any]] = {}


def service_contract(specification: str) -> Callable[[type[Any]], type[Any]]:
    """Pin a Protocol class to a Pelix specification name and register it."""

    def decorate(cls: type[Any]) -> type[Any]:
        existing = CONTRACTS.get(specification)
        if existing is not None and existing is not cls:
            raise ValueError(
                f"specification {specification!r} is already pinned to "
                f"{existing.__name__}"
            )
        setattr(cls, SPECIFICATION_FIELD, specification)
        CONTRACTS[specification] = cls
        return cls

    return decorate


def contract_for(specification: str) -> type[Any] | None:
    """Return the pinned contract for a service specification."""
    return CONTRACTS.get(specification)
