# Project memory and constraints

## Goal

This repository builds a plugin-driven LangChain agent using Pelix/iPOPO as the
component and service container. The final target covers frontend, backend,
agent loop, LLM, tools, and middleware as independently installable plugins.

Current milestone:

- plugin lifecycle management
- `agent.plugin.llm`
- `agent.plugin.tools`
- `agent.plugin.middleware`
- `agent.loop`

## Architecture constraints

- Plugins communicate through Pelix service specifications, not by importing
  each other's concrete classes.
- Public contracts live in `src/langharmess/contracts.py`.
- Plugin implementations live in `src/langharmess/plugins/`.
- The agent loop is an iPOPO component that rebuilds a LangChain
  `create_agent` graph when injected services change.
- Keep runtime plugin registration deterministic: production plugins must not
  use `@Instantiate`; the `PluginManager` controls instantiation and teardown.

## Quality gates

Every commit must pass:

```bash
make check
```

The gate order is Ruff -> mypy -> Pyright -> clean-process import check -> pytest.

- Unit test coverage must be at least 95%, enforced by pytest-cov.
- e2e tests must exercise the real Pelix/iPOPO framework and LangChain agent loop.
- Use TDD: write a failing test first, then the implementation.
- Do not weaken static analysis globally. Production modules stay strict.

The same gate is enforced locally by `.githooks/pre-commit` and in CI by
`.github/workflows/quality.yml`.

## Development environment

- Python 3.13.
- Use `.venv/bin/python`.
- Source package is `langharmess`.
- Install hooks with `make install-hooks`.

## File ownership

- Generated files (`plugin_registry.json`, caches, coverage reports) are not
  part of the reviewed source.
- Do not edit files inside `.venv/`.
