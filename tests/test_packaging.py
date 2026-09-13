"""Packaging configuration and script tests."""

from __future__ import annotations

import os
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_console_script_and_packaging_dependencies_are_declared() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert project["scripts"]["langharmess"] == "langharmess_cli.__main__:main"
    assert {"build>=1.3.0", "pyinstaller>=6.16.0"} <= set(
        project["optional-dependencies"]["packaging"]
    )
    package_data = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"][
        "setuptools"
    ]["package-data"]
    assert "config/langharmess.ini" in package_data["langharmess_config"]


def test_packaging_scripts_are_executable_and_valid_bash() -> None:
    for relative_path in ("scripts/build_packages.sh", "scripts/install.sh"):
        script = ROOT / relative_path
        assert os.access(script, os.X_OK)
        subprocess.run(["bash", "-n", script], check=True)
    installer = (ROOT / "scripts/install.sh").read_text()
    assert 'CONFIG_DIR=${LANG_HARMESS_HOME:-"$HOME/.langharmess"}' in installer
    assert "[providers.deepseek-v4-flash]" in installer
    template = (
        ROOT / "src/langharmess_config/config/langharmess.ini"
    ).read_text()
    assert "log_file" not in template
    builder = (ROOT / "scripts/build_packages.sh").read_text()
    assert "--collect-submodules langharmess_logging" in builder


def test_package_workflow_builds_all_supported_platforms() -> None:
    workflow = (ROOT / ".github/workflows/packages.yml").read_text()
    assert "macos:" in workflow
    assert "ubuntu:" in workflow
    assert "centos:" in workflow
    assert "dist/*.pkg" in workflow
    assert "dist/*.deb" in workflow
    assert "dist/*.rpm" in workflow
