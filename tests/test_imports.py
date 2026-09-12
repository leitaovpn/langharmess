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
    "langharmess.plugins.loop.llm.llm",
    "langharmess.plugins.loop.tools.tools",
    "langharmess.plugins.loop.middleware.template_middleware",
    "langharmess.plugins.loop.system_prompt.template_system_prompt",
    "langharmess.plugins.loop.response_format.template_response_format",
    "langharmess.plugins.loop.state_schema.template_state_schema",
    "langharmess.plugins.loop.context_schema.template_context_schema",
    "langharmess.plugins.loop.checkpointer.template_checkpointer",
    "langharmess.plugins.loop.store.template_store",
    "langharmess.plugins.loop.interrupt_before.template_interrupt_before",
    "langharmess.plugins.loop.interrupt_after.template_interrupt_after",
    "langharmess.plugins.loop.debug.template_debug",
    "langharmess.plugins.loop.name.template_name",
    "langharmess.plugins.loop.cache.template_cache",
    "langharmess.plugins.loop.transformers.template_transformers",
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
