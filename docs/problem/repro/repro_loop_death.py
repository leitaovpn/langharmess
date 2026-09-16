"""Deterministic repro: does llm kill/rebind eventually kill the agent loop?

Mirrors the real run: each /stream with changed llm properties triggers
ensure_plugin_instance -> kill + re-instantiate of the scoped llm, which is a
REQUIRED dependency of the agent loop. We probe loop liveness after every step.
"""

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests"))
from fixtures.fake_llm_server import FakeLLMServer  # noqa: E402

PYTHON = str(ROOT / ".venv" / "bin" / "python")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_health(base_url: str) -> bool:
    for _ in range(300):
        try:
            if httpx.get(f"{base_url}/health", timeout=1.0).status_code < 500:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    return False


def main() -> None:
    fake = FakeLLMServer()
    fake.start()
    tmp = tempfile.mkdtemp(prefix="lh-repro-")
    (Path(tmp) / "langharmess.toml").write_text(
        "\n".join(
            [
                "[providers.fake]",
                'protocol = "chat"',
                f'base_url = "{fake.base_url}"',
                'model = "fake-model"',
                'api_key = "test-key"',
                "",
            ]
        )
    )
    env = os.environ.copy()
    env["LANG_HARMESS_DIR"] = tmp
    env["PYTHONPATH"] = str(ROOT / "src")
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    server = subprocess.Popen(
        [
            PYTHON,
            "-m",
            "uvicorn",
            "langharmess_api.common.server:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert wait_health(base_url), "server did not start"
        fake_url = fake.base_url
        # (label, model, api_key, base_url)
        sequence = [
            ("A1", "fake-model", "test-key", fake_url),
            ("A2", "fake-model", "test-key", fake_url),
            ("B1", "fake-model-B", "test-key", fake_url),
            ("B2", "fake-model-B", "test-key", fake_url),
            ("C1", "fake-model-C", "test-key", fake_url),
            ("C2", "fake-model-C", "test-key", fake_url),
            ("D1", "fake-model-C", "", ""),  # killer shape: key/url stripped
            ("D2", "fake-model-C", "", ""),
            ("E1", "fake-model", "test-key", fake_url),
        ]
        for index, (label, model, key, url) in enumerate(sequence):
            before = len(fake.requests)
            response = httpx.post(
                f"{base_url}/stream",
                json={
                    "input": f"probe {label}",
                    "model": model,
                    "api_key": key,
                    "base_url": url,
                    "protocol": "chat",
                    "user_id": "repro_user",
                    "agent_id": "simple_agent",
                    "session_id": f"repro-{label}",
                },
                headers={"Authorization": "Bearer secret"},
                timeout=30.0,
            )
            reached = len(fake.requests) > before
            status = response.status_code
            detail = ""
            if status != 200:
                detail = response.json().get("detail", "")
            print(
                f"{label}: status={status} reached_llm={reached} detail={detail!r}",
                flush=True,
            )
            if status == 503:
                print(f"LOOP DIED at step {label} (index {index})", flush=True)
                break
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        fake.stop()


if __name__ == "__main__":
    main()
