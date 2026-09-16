"""Deterministic repro: consecutive identical stream deltas lose one chunk.

Fake LLM emits "scope-marker-7" then "7" as two separate chunks.
Expected (from provider): "scope-marker-77". Checkpoint will hold the full text;
the forwarded assistant events will be missing the second chunk.
"""

import asyncio
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
PYTHON = str(ROOT / ".venv" / "bin" / "python")


class ChunkPairServer(ThreadingHTTPServer):
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        if not payload.get("stream"):
            body = json.dumps(
                {
                    "id": "x",
                    "object": "chat.completion",
                    "created": 1,
                    "model": "fake",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": "scope-marker-77",
                            },
                            "finish_reason": "stop",
                        }
                    ],
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()

        def chunk(text: str) -> dict:
            return {
                "id": "x",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "fake",
                "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
            }

        for text in ["scope", "-marker", "-", "7", "7"]:  # last two deltas are identical
            self.wfile.write(f"data: {json.dumps(chunk(text))}\n\n".encode())
            self.wfile.flush()
        done = chunk("")
        done["choices"][0]["finish_reason"] = "stop"
        self.wfile.write(f"data: {json.dumps(done)}\n\ndata: [DONE]\n\n".encode())
        self.wfile.flush()

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def main() -> None:
    llm_port = free_port()
    llm = ChunkPairServer(("127.0.0.1", llm_port), Handler)
    threading.Thread(target=llm.serve_forever, daemon=True).start()
    llm_url = f"http://127.0.0.1:{llm_port}/v1"

    tmp = tempfile.mkdtemp(prefix="lh-chunks-")
    (Path(tmp) / "langharmess.toml").write_text(
        "\n".join(
            [
                "[providers.fake]",
                'protocol = "chat"',
                f'base_url = "{llm_url}"',
                'model = "fake"',
                'api_key = "test-key"',
                "",
            ]
        )
    )
    env = os.environ.copy()
    env["LANG_HARMESS_DIR"] = tmp
    env["PYTHONPATH"] = str(ROOT / "src")
    port = free_port()
    base = f"http://127.0.0.1:{port}"
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
        for _ in range(300):
            try:
                if httpx.get(f"{base}/health", timeout=1.0).status_code < 500:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        text = ""
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{base}/stream",
                json={
                    "input": "echo marker",
                    "model": "fake",
                    "api_key": "test-key",
                    "base_url": llm_url,
                    "protocol": "chat",
                    "user_id": "chunk_user",
                    "agent_id": "simple_agent",
                    "session_id": "chunk-session",
                },
                headers={"Authorization": "Bearer secret"},
            ) as response:
                async for line in response.aiter_lines():
                    event = json.loads(line)
                    if event.get("type") == "assistant":
                        text += event.get("content", "")
                        print("  assistant delta:", repr(event.get("content")), flush=True)
        print("provider sent   : 'scope-marker-77'", flush=True)
        print("streamed text   :", repr(text), flush=True)
        print("BUG PRESENT     :", text != "scope-marker-77", flush=True)
    finally:
        server.terminate()
        server.wait(timeout=10)
        llm.shutdown()


asyncio.run(main())
