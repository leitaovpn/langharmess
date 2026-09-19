"""Minimal repro: bare openai SDK against the gateway, responses vs chat endpoint."""

import asyncio
import sys
import tomllib
from pathlib import Path

from openai import AsyncOpenAI

config = tomllib.loads(Path("langharness.toml").read_text())
provider = config["providers"]["chatgpt-5"]

client = AsyncOpenAI(
    api_key=provider["api_key"],
    base_url=provider["base_url"],
)


async def try_responses(stream: bool) -> None:
    print(f"--- POST /responses (stream={stream}) ---", flush=True)
    try:
        kwargs = {
            "model": provider["model"],
            "input": "Hello",
        }
        if stream:
            async with client.responses.stream(**kwargs) as response:
                await response.anext()
        else:
            await client.responses.create(**kwargs)
        print("OK", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(type(exc).__name__, str(exc)[:400], flush=True)


async def try_chat() -> None:
    print("--- POST /chat/completions ---", flush=True)
    try:
        response = await client.chat.completions.create(
            model=provider["model"],
            messages=[{"role": "user", "content": "Hello"}],
        )
        print("OK:", response.choices[0].message.content, flush=True)
    except Exception as exc:  # noqa: BLE001
        print(type(exc).__name__, str(exc)[:400], flush=True)


async def main() -> None:
    await try_responses(stream=True)
    await try_responses(stream=False)
    await try_chat()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
