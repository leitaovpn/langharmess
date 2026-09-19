"""Public logging plugin contract."""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from langharness_plugin.validation import service_contract

SPEC_LOG = "log.plugin"


@service_contract(SPEC_LOG)
@runtime_checkable
class LogProvider(Protocol):
    def get_logger(self) -> logging.Logger: ...
