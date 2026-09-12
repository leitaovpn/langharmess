# Project memory and constraints

## Goal

This repository builds a plugin-driven agent system using Pelix/iPOPO as the
component and service container. It currently covers the agent loop, plugin
lifecycle, an API server, and a CLI, all assembled from independently
installable plugins.

Current milestone:

- plugin lifecycle management
- `agent.plugin.llm`
- `agent.plugin.tools`
- `agent.plugin.middleware`
- `agent.loop`
- `api.server`
- `api.plugin.auth`
- `api.plugin.rate_limit`
- `api.plugin.db`
- `api.plugin.route`
- `cli.plugin.command`

## Architecture constraints

- Plugins communicate through Pelix service specifications, not by importing
  each other's concrete classes.
- Public agent contracts live in `src/langharmess_core/contracts.py`.
- Plugin lifecycle and registration live in `src/langharmess_plugin/`.
- Agent plugins live in `src/langharmess_core/plugins/loop/`.
- API plugins live in `src/langharmess_api/plugins/`.
- CLI command plugins live in `src/langharmess_cli/plugins/commands/`.
- The agent loop is an iPOPO component that rebuilds a LangChain
  `create_agent` graph when injected services change.
- Keep runtime plugin registration deterministic: production plugins must not
  use `@Instantiate`; the `PluginManager` controls instantiation and teardown.

## Packages

- `langharmess_core`: agent loop and agent plugin contracts/implementations.
- `langharmess_plugin`: plugin manager and registry.
- `langharmess_api`: plugin-driven FastAPI server.
- `langharmess_cli`: plugin-driven CLI with API auto-start.

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
- Source packages are `langharmess_core`, `langharmess_plugin`,
  `langharmess_api`, and `langharmess_cli`.
- Install hooks with `make install-hooks`.

## File ownership

- Generated files (`plugin_registry.json`, caches, coverage reports) are not
  part of the reviewed source.
- Do not edit files inside `.venv/`.
