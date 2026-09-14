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
    "langharmess_core.plugin",
    "langharmess_core.common.dependencies",
    "langharmess_plugin",
    "langharmess_plugin.registry",
    "langharmess_plugin.plugin_manager",
    "langharmess_plugin.validation",
    "langharmess_core.plugins",
    "langharmess_core.plugins.loop",
    "langharmess_core.plugins.loop.agent_loop",
    "langharmess_core.plugins.llm.llm",
    "langharmess_core.plugins.tools.tools",
    "langharmess_core.plugins.tools.workspace",
    "langharmess_core.plugins.middleware.template_middleware",
    "langharmess_core.plugins.system_prompt.template_system_prompt",
    "langharmess_core.plugins.response_format.template_response_format",
    "langharmess_core.plugins.state_schema.template_state_schema",
    "langharmess_core.plugins.context_schema.template_context_schema",
    "langharmess_core.plugins.checkpointer.template_checkpointer",
    "langharmess_core.plugins.checkpointer.sqlite",
    "langharmess_core.plugins.store.template_store",
    "langharmess_core.plugins.interrupt_before.template_interrupt_before",
    "langharmess_core.plugins.interrupt_after.template_interrupt_after",
    "langharmess_core.plugins.debug.template_debug",
    "langharmess_core.plugins.name.template_name",
    "langharmess_core.plugins.cache.template_cache",
    "langharmess_core.plugins.transformers.template_transformers",
    "langharmess_config.plugin",
    "langharmess_logging.plugin",
    "langharmess_logging.plugins.log",
    "langharmess_api",
    "langharmess_api.plugin",
    "langharmess_api.common.server",
    "langharmess_api.plugins",
    "langharmess_api.plugins.server.app",
    "langharmess_cli",
    "langharmess_cli.plugin",
    "langharmess_cli.common.api_guard",
    "langharmess_cli.common.cli",
    "langharmess_cli.common.i18n",
    "langharmess_cli.common.interactive",
    "langharmess_cli.common.runner",
    "langharmess_cli.plugins",
    "langharmess_cli.plugins.commands.health",
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
