"""Detects and auto-starts the API server."""

from __future__ import annotations

import atexit
import subprocess
import sys
import time
from urllib.parse import urlparse

import httpx


class APIGuard:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11534",
        *,
        config_dir: str | None = None,
        startup_timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.config_dir = config_dir
        self.startup_timeout = startup_timeout
        self._process: subprocess.Popen[bytes] | None = None

    def is_running(self) -> bool:
        try:
            response = httpx.get(f"{self.base_url}/health", timeout=1.0)
            return response.status_code < 500
        except httpx.HTTPError:
            return False

    def ensure_api_server(self) -> None:
        if self.is_running():
            return

        parsed = urlparse(self.base_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 11534

        if getattr(sys, "frozen", False):
            # A frozen executable cannot spawn `python -m`; serve in-process.
            from langharness.__main__ import main as serve

            command = [
                "--mode",
                "server",
                "--server-ip",
                host,
                "--server-port",
                str(port),
            ]
            if self.config_dir is not None:
                command.extend(["--config-dir", self.config_dir])
            serve(command)
            return

        command = [
            sys.executable,
            "-m",
            "langharness",
            "--mode",
            "server",
            "--server-ip",
            host,
            "--server-port",
            str(port),
        ]
        if self.config_dir is not None:
            command.extend(["--config-dir", self.config_dir])
        self._process = subprocess.Popen(command)
        atexit.register(self._terminate)

        deadline = time.monotonic() + self.startup_timeout
        while time.monotonic() < deadline:
            if self.is_running():
                return
            time.sleep(0.1)

        self._process.terminate()
        self._process = None
        raise RuntimeError("API server did not become ready in time")

    def _terminate(self) -> None:
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
