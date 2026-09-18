# langharmess-core

Plugin-driven LangChain agent using Pelix/iPOPO.

See [AGENTS.md](AGENTS.md) for project constraints and development gates.

## Installation and packaging

Installing the Python package exposes the CLI directly:

```bash
python -m pip install .
langharmess --help
```

Build a native package on the target operating system:

```bash
python -m pip install -e ".[packaging]"
scripts/build_packages.sh
```

The build produces a self-contained executable with an embedded Python runtime:

- macOS: `.pkg` and `.tar.gz`
- Ubuntu/Debian: `.deb` and `.tar.gz`
- CentOS/RHEL: `.rpm` and `.tar.gz`

Install one generated artifact with:

```bash
scripts/install.sh dist/<artifact>
```

Set `LANG_HARMESS_MODEL`, `LANG_HARMESS_API_KEY`, and
`LANG_HARMESS_BASE_URL` before starting `langharmess`.

The default configuration and separate CLI/server logs are created under
`~/.langharmess`:

```text
~/.langharmess/
├── langharmess.toml
├── langharmess_cli.log
└── langharmess_server.log
```

The configuration template is:

```toml
[DEFAULT]

# Default model used when interactive mode starts without --provider.
# [providers.default]
# protocol = "chat"
# base_url = "https://api.example.com/v1"
# model = "your-model"
# api_key = "your-api-key"
```

Uncomment and fill in `[providers.default]` to select the model interactive
mode uses at startup. Without it, interactive mode fails with an error;
`--provider <name>` selects one of the other configured providers instead.
`default` is a reserved provider name: it is hidden from `/model` and cannot
be selected with `--provider` or `/model`.

Optionally select a configured model provider and override the common data
directory:

```bash
langharmess --provider demo --dir /data/langharmess
```

`--dir` controls the location of the TOML file and both log files.

Each provider selects one LangChain client protocol: `chat` for the
OpenAI-compatible Chat Completions API, `responses` for the OpenAI Responses
API, or `anthropic` for the Anthropic Messages API. In interactive mode,
`/model` lists providers and `/model <provider_name>` switches the active
provider for subsequent requests. Switching to a different provider starts a
new conversation session so checkpointed messages cannot leak across models.

Interactive mode uses `prompt_toolkit` for persistent history, slash-command
completion, keyboard handling, and the model status toolbar. Rich renders the
welcome panel, streaming Markdown responses, tool calls, tool output, and
errors. Slash commands remain plugin-provided through `InteractiveCommandSpec`;
the completer discovers every registered command without UI-specific plugin
code. The Rich renderer is also an iPOPO service and can be replaced by another
`cli.plugin.renderer` implementation.

## Interactive commands

### `/plugins`

Manage runtime and configuration plugins. Two scope vocabularies apply:
**runtime scopes** (`root`, `server`, `ui`, `agent`, `agent:<id>`) for
installed runtime plugin instances, and **configuration scopes** (`api`,
`cli`, `agent:<id>`) for persisted overrides. Every mutation requires an
explicit scope; omitting or misspelling it prints the error plus usage
instead of silently targeting the wrong scope.

```text
/plugins discover                                   # rescan and list discoverable packages
/plugins list [runtime_scope]                       # runtime plugins; omit scope for all scopes (Scope column shown)
/plugins enable|disable <runtime_scope> <plugin>    # toggle a runtime plugin
/plugins runtime set <scope> <plugin> KEY=VALUE ...  # update dynamic properties at runtime
/plugins install <package_id> <contribution_id> <scope>
/plugins uninstall <scope> <plugin>
/plugins config [config_scope]                      # persisted overrides; omit scope for all scopes
/plugins config enable|disable <config_scope> <plugin>
/plugins set <config_scope> <plugin> KEY=VALUE
/plugins history <config_scope>
/plugins rollback <config_scope> <version>
```

`list` and `config` aggregate every scope when the scope argument is
omitted. `history` and `rollback` require a configuration scope — they no
longer default to `api`. The same operations are available non-interactively
via `langharmess plugins <action> ... --scope <scope>` (and `langharmess
scope` prints the tree as JSON).

### `/scope`

Shows the runtime scope tree served by the API:

```text
root
├── server
├── ui
└── agent
    └── agent:<agent_id>
```

### Other slash commands

- `/model` — list configured providers; `/model <provider>` switches the
  active provider (starts a new session so checkpointed messages cannot
  leak across models)
- `/agents` — list agents available on the API server
- `/agent [<agent_id>]` — show or switch the active agent
- `/sessions` — list recent sessions for the current user
- `/new` — start a fresh session with the next message
- `/whoami` — show user, agent, and session identity
- `/help`, `/exit` — built-in shell commands
