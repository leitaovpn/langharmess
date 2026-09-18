"""Compatibility entrypoint delegating to the unified bootstrap."""

from langharness.__main__ import main as main

if __name__ == "__main__":
    raise SystemExit(main())
