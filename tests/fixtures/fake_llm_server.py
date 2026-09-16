"""Deterministic OpenAI-compatible LLM server for real CLI tests."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return str(content or "")


class FakeLLMServer:
    """Serves scripted chat completions and records every incoming message."""

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        tool_trigger: str = "USE_TOOL",
        tool_name: str = "real_echo",
    ) -> None:
        self.host = host
        self.port = port
        self.tool_trigger = tool_trigger
        self.tool_name = tool_name
        self.requests: list[dict[str, Any]] = []
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        if self._server is None:
            raise RuntimeError("FakeLLMServer is not started")
        return f"http://{self.host}:{self._server.server_address[1]}/v1"

    @property
    def messages(self) -> list[dict[str, Any]]:
        """All messages observed across all chat completion requests."""
        return [
            dict(message)
            for request in self.requests
            for message in request.get("messages", [])
            if isinstance(message, dict)
        ]

    def start(self) -> None:
        if self._server is not None:
            return

        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                if not self.path.endswith(
                    ("/chat/completions", "/v1/chat/completions")
                ):
                    self.send_error(404)
                    return
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                owner.requests.append(payload)
                if payload.get("stream"):
                    self._send_stream(payload)
                else:
                    self._send_json(payload)

            def _send_json(self, payload: dict[str, Any]) -> None:
                body = json.dumps(owner._response_for(payload)).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_stream(self, payload: dict[str, Any]) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                for event in owner._stream_events(payload):
                    self.wfile.write(
                        f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode()
                    )
                    self.wfile.flush()
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()

            def log_message(self, format: str, *args: Any) -> None:
                return

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="fake-llm-server",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._server = None
        self._thread = None

    def _response_for(self, payload: dict[str, Any]) -> dict[str, Any]:
        messages = payload.get("messages") or []
        if any(message.get("role") == "tool" for message in messages):
            tool_messages = [
                message for message in messages if message.get("role") == "tool"
            ]
            last_output = _content_text(tool_messages[-1].get("content"))
            content = f"final:{last_output}"
            return self._completion(content)

        user_messages = [
            message for message in messages if message.get("role") == "user"
        ]
        last_user = _content_text(user_messages[-1].get("content")) if user_messages else ""
        if self.tool_trigger in last_user:
            return self._tool_completion()
        return self._completion(f"echo:{last_user}")

    def _stream_events(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        messages = payload.get("messages") or []
        if any(message.get("role") == "tool" for message in messages):
            tool_messages = [
                message for message in messages if message.get("role") == "tool"
            ]
            last_output = _content_text(tool_messages[-1].get("content"))
            return self._content_stream_events(f"final:{last_output}")

        user_messages = [
            message for message in messages if message.get("role") == "user"
        ]
        last_user = _content_text(user_messages[-1].get("content")) if user_messages else ""
        if self.tool_trigger in last_user:
            return self._tool_stream_events()
        return self._content_stream_events(f"echo:{last_user}")

    def _content_stream_events(self, content: str) -> list[dict[str, Any]]:
        return [
            self._chunk({"role": "assistant", "content": ""}, None),
            self._chunk({"content": content}, None),
            self._chunk({}, "stop"),
        ]

    def _tool_stream_events(self) -> list[dict[str, Any]]:
        return [
            self._chunk(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call_real_echo",
                            "type": "function",
                            "function": {
                                "name": self.tool_name,
                                "arguments": "",
                            },
                        }
                    ],
                },
                None,
            ),
            self._chunk(
                {
                    "tool_calls": [
                        {
                            "index": 0,
                            "function": {
                                "arguments": json.dumps({"text": "ping"}),
                            },
                        }
                    ]
                },
                None,
            ),
            self._chunk({}, "tool_calls"),
        ]

    @staticmethod
    def _chunk(delta: dict[str, Any], finish_reason: str | None) -> dict[str, Any]:
        return {
            "id": "chatcmpl-fake",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "fake-model",
            "choices": [
                {
                    "index": 0,
                    "delta": delta,
                    "finish_reason": finish_reason,
                }
            ],
        }

    def _completion(self, content: str) -> dict[str, Any]:
        return {
            "id": "chatcmpl-fake",
            "object": "chat.completion",
            "created": 1,
            "model": "fake-model",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
        }

    def _tool_completion(self) -> dict[str, Any]:
        return {
            "id": "chatcmpl-fake-tool",
            "object": "chat.completion",
            "created": 1,
            "model": "fake-model",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_real_echo",
                                "type": "function",
                                "function": {
                                    "name": self.tool_name,
                                    "arguments": json.dumps({"text": "ping"}),
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
        }

    def __enter__(self) -> FakeLLMServer:
        self.start()
        return self

    def __exit__(self, *_args: Any) -> None:
        self.stop()
