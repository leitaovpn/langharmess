"""End-to-end tests for the plugin-driven CLI."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

SOURCE_DIR = Path(__file__).resolve().parents[1] / "src"
ENV = {**os.environ, "PYTHONPATH": str(SOURCE_DIR)}


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_health(base_url: str, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            httpx.get(f"{base_url}/health", timeout=1.0)
            return True
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    return False


def test_cli_auto_starts_api_server() -> None:
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    result = subprocess.run(
        [sys.executable, "-m", "langharmess_cli", "health", "--base-url", base_url],
        env=ENV,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "'status': 'ok'" in result.stdout


def test_cli_reuses_running_api_server() -> None:
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "langharmess_api.server:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=ENV,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert wait_for_health(base_url)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "langharmess_cli",
                "health",
                "--base-url",
                base_url,
            ],
            env=ENV,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert "'status': 'ok'" in result.stdout
    finally:
        server.terminate()
        server.wait(timeout=10)


def test_cli_interactive_mode(tmp_path: Path) -> None:
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "langharmess_cli",
            "interactive",
            "--dir",
            str(tmp_path),
            "--base-url",
            base_url,
        ],
        env=ENV,
        input="/health\nexit\n",
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "{'status': 'ok', 'db': True}" in result.stdout
    assert "Started server process" not in result.stdout
    assert "Started server process" not in result.stderr
    assert (tmp_path / "langharmess.toml").is_file()
    assert "CLI started" in (tmp_path / "langharmess_cli.log").read_text()
    server_log = (tmp_path / "langharmess_server.log").read_text()
    assert "API server app built" in server_log
    assert "Started server process" in server_log
    assert "GET /health" in server_log
