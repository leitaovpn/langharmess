"""Clean-process import checks for public modules."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SOURCE_DIR = Path(__file__).resolve().parents[1] / "src"
PUBLIC_MODULES = [
    "langharmess_core",
    "langharmess_core.contracts",
    "langharmess_plugin",
    "langharmess_plugin.registry",
    "langharmess_plugin.plugin_manager",
    "langharmess_core.agent_loop",
    "langharmess_core.plugins",
    "langharmess_core.plugins.loop.llm.llm",
    "langharmess_core.plugins.loop.tools.tools",
    "langharmess_core.plugins.loop.tools.workspace",
    "langharmess_core.plugins.loop.middleware.template_middleware",
    "langharmess_core.plugins.loop.system_prompt.template_system_prompt",
    "langharmess_core.plugins.loop.response_format.template_response_format",
    "langharmess_core.plugins.loop.state_schema.template_state_schema",
    "langharmess_core.plugins.loop.context_schema.template_context_schema",
    "langharmess_core.plugins.loop.checkpointer.template_checkpointer",
    "langharmess_core.plugins.loop.checkpointer.sqlite",
    "langharmess_core.plugins.loop.store.template_store",
    "langharmess_core.plugins.loop.interrupt_before.template_interrupt_before",
    "langharmess_core.plugins.loop.interrupt_after.template_interrupt_after",
    "langharmess_core.plugins.loop.debug.template_debug",
    "langharmess_core.plugins.loop.name.template_name",
    "langharmess_core.plugins.loop.cache.template_cache",
    "langharmess_core.plugins.loop.transformers.template_transformers",
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
