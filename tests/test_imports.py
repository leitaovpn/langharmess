"""Clean-process import checks for public modules."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SOURCE_DIR = Path(__file__).resolve().parents[1] / "src"
PUBLIC_MODULES = [
    "langharmess",
    "langharmess.contracts",
    "langharmess.registry",
    "langharmess.plugin_manager",
    "langharmess.agent_loop",
    "langharmess.plugins",
    "langharmess.plugins.llm",
    "langharmess.plugins.tools",
    "langharmess.plugins.middleware",
]


def test_public_modules_import_in_clean_process() -> None:
    env = {**os.environ, "PYTHONPATH": str(SOURCE_DIR)}
    for module in PUBLIC_MODULES:
        result = subprocess.run(
            [sys.executable, "-c", f"import {module}"],
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"{module} failed:\n{result.stderr}"
