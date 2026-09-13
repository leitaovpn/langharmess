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

[providers.deepseek-v4-flash]
protocol = "chat"
base_url = "xxxxx"
model = "xxxxx"
api_key = "xxxx"
```

Optionally select a configured model provider and override the common data
directory:

```bash
langharmess --provider deepseek-v4-flash --dir /data/langharmess
```

`--dir` controls the location of the TOML file and both log files. Existing
`LANG_HARMESS_MODEL`, `LANG_HARMESS_API_KEY`, and `LANG_HARMESS_BASE_URL` values
remain the fallback when no provider is configured. When `--provider` is
omitted and the TOML file contains providers, the CLI randomly selects one for
the session.

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
