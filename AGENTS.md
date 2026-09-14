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
- The agent loop is an iPOPO component that rebuilds a LangChain
  `create_agent` graph when injected services change.
- Keep runtime plugin registration deterministic: production plugins must not
  use `@Instantiate`; the `PluginManager` controls instantiation and teardown.

### Module file layout

Every runtime module (`langharmess_core`, `langharmess_api`,
`langharmess_cli`, `langharmess_config`, `langharmess_logging`) follows one
layout:

```text
<module>/
├── __init__.py
├── __main__.py          # thin entrypoint only (api/cli); CLI and API server
├── contracts.py         # SPEC_* constants and Provider protocols
├── plugin.py            # plugin descriptors and assembly helpers
├── common/              # assembly helpers shared with entrypoints
└── plugins/             # plugin implementations, one topic per directory
    └── <topic>/
        └── <name>.py    # component factory + iPOPO component
```

Rules:

- `plugin.py` is the only place that builds `PluginDescriptor` objects;
  entrypoints join `config`/`log`/module descriptor lists but never inline
  `PluginDescriptor(...)` literals.
- `plugins/<topic>/` owns the component implementation. One-topic modules may
  use `plugins/<name>.py` directly (e.g.
  `langharmess_logging/plugins/log.py`, `langharmess_cli/plugins/rich_renderer.py`).
- `common/` holds assembly helpers: CLI and server entry logic, API guards,
  the interactive runner, i18n, and shared FastAPI dependency sentinels.
- Descriptor `module=` strings and factory names must match the moved paths;
  prefer naming a factory `<name>-plugin-factory` so it tracks its file.
- The agent loop component is `langharmess_core/plugins/loop/agent_loop.py`;
  the FastAPI component is `langharmess_api/plugins/server/app.py` with the
  server factory in `langharmess_api/common/server.py`.
- Tests import public paths; keep `tests/test_imports.py` `PUBLIC_MODULES`
  in sync when modules move.
- `langharmess_plugin/` is the framework layer and keeps its flat layout
  (`contracts.py`, `registry.py`, `plugin_manager.py`).

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

### Real end-to-end testing

`tests/test_e2e.py` covers the plugin framework with fake models. To verify
the real path (real provider, real agent loop, real tools) use this workflow:

1. Run one protocol per pass, each in an isolated workspace that doubles as
   the server cwd, so one run cannot poison the next:
   ```bash
   cd /tmp/rag-ws/chat                       # workspace with the input files
   .venv/bin/python -m langharmess_api --host 127.0.0.1 --port 8100 &
   .venv/bin/python driver.py chat           # POST /stream, collect NDJSON
   ```
2. Call `POST /stream` with `{input, model, api_key, base_url, session_id,
   protocol}` where `protocol` is `chat`, `anthropic`, or `responses`;
   authenticate with `Authorization: Bearer <plugin.token>` (default
   `secret`). The server binds the workspace tools to its cwd, so start it
   in the workspace that holds the test data.
3. Read the raw NDJSON events: `assistant` (text deltas), `tool_call`,
   `tool_output`, `usage`, and `error`. Runtime failures arrive as an
   `error` event inside an HTTP 200 stream — always scan for it instead of
   trusting the status code. `agent_loop.astream` catches exceptions and
   turns them into error events.
4. Verify results twice: the produced artifact (e.g. `answer.json`) and the
   conversation state (see below). Prefer the artifact because it is what
   the task actually asked for.

Inspect what the agent actually sent and stored:

```python
import asyncio, aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

async def dump(db, thread):
    saver = AsyncSqliteSaver(aiosqlite.connect(db))
    tup = await saver.aget_tuple({"configurable": {"thread_id": thread}})
    for m in tup.checkpoint["channel_values"]["messages"]:
        print(type(m).__name__, getattr(m, "tool_calls", None), str(m.content)[:120])
```

Pitfalls learned from real runs:

- Keep each test workspace clean (input files only). `list_directory` returns
  everything in the cwd, so stray artifacts derail the agent into exploring
  them; a big sibling directory once made one run burn 390k tokens.
- Before blaming the product, check the input: a corrupted or high-entropy
  `sales.xlsx` made agents do binary forensics and never finish the task.
  Validate test data with a real reader (openpyxl) before each pass.
- The `langchain_community` file tools resolve `root_dir` relative to the
  process cwd at call time; deleting a running server's cwd yields a bare
  `FileNotFoundError` that aborts the stream.
- A tool raising an exception fails the whole request: the error is returned
  as a stream error, not fed back to the model as a tool result.
- Streaming aggregators keep partial tool-call fragments in `AIMessage.content`
  (completed calls also land in `tool_calls`); the anthropic protocol replays
  content verbatim, so orphan fragments must be stripped. See
  `_strip_orphan_tool_use` in `agent_loop.py` and `tests/test_agent_loop_tool_fragments.py`.
- Run a multi-call turn on all three protocols; `chat`/`responses` keep calls
  in a separate `tool_calls` field while `anthropic` embeds them in content,
  so protocol-specific breakage only shows up on that protocol.
- One server per port per pass; kill leftover servers before restarting, and
  never `rm -rf` a directory a server is still running from. Sessions are
  isolated only by `session_id`, so give every pass its own id.

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
