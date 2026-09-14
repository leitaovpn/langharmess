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
- Modules follow one layout: `plugin.py` builds plugin descriptors, `plugins/`
  holds the component implementations (one topic per directory), and
  `common/` holds assembly helpers shared with entrypoints.
- Agent plugins live in `src/langharmess_core/plugins/`; the agent loop
  component is `src/langharmess_core/plugins/loop/agent_loop.py`.
- API plugins live in `src/langharmess_api/plugins/`; the FastAPI component is
  `src/langharmess_api/plugins/server/app.py` and the server factory is
  `src/langharmess_api/common/server.py`.
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

### Debugging

- Entry points: `.venv/bin/python -m langharmess_cli` (CLI) and
  `.venv/bin/python -m langharmess_api` (API server). The package is
  installed editable into `.venv`, so no `PYTHONPATH` setup is needed.
  Ready-made configurations live in `.vscode/launch.json`.
- Interactive mode uses prompt_toolkit and needs a real TTY: debug it with
  `"console": "integratedTerminal"`.
- The interactive CLI auto-starts the API server as a subprocess
  (`langharmess_cli.common.api_guard.APIGuard`); a debugger attached to the CLI
  does not follow into it. To debug the server, launch the "API server"
  configuration separately or use the "full stack" compound — the CLI reuses
  an already-running server.
- Without `--provider` the CLI picks a random provider from
  `~/.langharmess/langharmess.toml`; pass `--provider` for deterministic
  sessions.

### CodeGraph index

The CodeGraph MCP server (`codegraph_*` tools) and the `codegraph` CLI are
available. The MCP server runs as `codegraph serve --mcp` (configured in
`~/.claude.json`, no `--path`), so it resolves the project from the session's
workspace root.

When to run:

- First session in a project: MCP tools fail with "No CodeGraph project is
  loaded" / "not initialized", or `.codegraph/` does not exist.
- After cloning the repository on a new machine (the index is local-only).

How to initialize and index:

```bash
cd <project-root>
codegraph init -i   # creates .codegraph/ (with its own .gitignore) and builds the initial index
codegraph index -f  # optional: force full re-index, e.g. after tooling changes
codegraph sync      # incremental update; normally automatic via the MCP file watcher
```

Add `.codegraph/` to the root `.gitignore`: `init` only ignores the files
inside it, so the directory itself still shows as untracked.

How to verify:

- `codegraph status` reports files/nodes/edges and "Index is up to date".
- MCP: `codegraph_status` returns the same stats; spot-check with
  `codegraph_search <symbol>` or `codegraph_files`.
- If MCP tools still report "No CodeGraph project is loaded": pass
  `projectPath` in the tool call, or add `--path <project-root>` to the
  codegraph MCP server args in the agent configuration.

Once indexed, prefer the MCP tools over grep/read for structural questions:
`codegraph_context` for task context, `codegraph_trace` for call flows,
`codegraph_search` for symbols, `codegraph_files` for structure.

## Lessons learned

- The CLI renderer (`langharmess_cli.plugins.rich_renderer`) draws the
  streamed answer in a `rich.live.Live` region. Keep the live frame shorter
  than the terminal: with `vertical_overflow="visible"`, once the frame
  outgrows the terminal, cursor-up control codes clamp at the top row and
  every re-render duplicates the whole frame into the scrollback. The
  renderer commits overflowing head segments to plain output before each
  refresh (`_commit_overflow`, `LIVE_MARGIN = 3` slack) and uses
  `vertical_overflow="crop"` as a safety net.
- Terminal output is verified through emulation, not raw byte streams: live
  redraws always re-emit visible text (erased in place by control codes), so
  substring counts in raw output cannot distinguish correct redraws from
  duplicated output. `tests/test_rich_renderer.py` ships a minimal VT100
  emulator (`_TerminalEmulator` / `terminal_lines`) for these assertions.

## File ownership

- Generated files (`plugin_registry.json`, caches, coverage reports, the
  `.codegraph/` index) are not part of the reviewed source.
- Do not edit files inside `.venv/`.
