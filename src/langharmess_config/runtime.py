"""Runtime helpers backed by the aggregated configuration service."""

from __future__ import annotations

import logging
from pathlib import Path


def configure_logging(log_file: str) -> Path:
    path = Path(log_file).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=path,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )
    return path
