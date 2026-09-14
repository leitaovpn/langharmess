"""API server entrypoint."""

from __future__ import annotations

from argparse import ArgumentParser


def main(argv: list[str] | None = None) -> int:
    import uvicorn

    from langharmess_api.common.server import create_app

    parser = ArgumentParser(description="langharmess API server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    uvicorn.run(create_app(), host=args.host, port=args.port, log_config=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
