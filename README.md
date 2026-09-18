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

### 管理工具(给 agent loop 用的 plugin/scope 操作)

`management-tools` 是一个可动态安装的 `agent.plugin.tools` 插件,把
`/plugins`(运行时面)与 `/scope` 的操作包装成 9 个 LangChain 工具,供
agent loop 的 LLM 调用:

| 工具 | 说明 |
| --- | --- |
| `list_scope_tree` | 查看运行时作用域树 |
| `list_runtime_plugins` | 列出已装运行时插件(可按 scope 过滤) |
| `discover_plugins` | 重新扫描并列出可发现包 |
| `install_plugin` | 安装发现的插件贡献(必须显式 scope,初始 disabled) |
| `enable_plugin` / `disable_plugin` | 按 (name, scope) 启停插件 |
| `upgrade_plugin` | 升级到包最新版本 |
| `uninstall_plugin` | 卸载并删除持久化注册 |
| `update_plugin_properties` | 更新运行时属性(runtime set) |

每个工具的 description 写明用途、使用时机与 scope 约束;危险操作带
入参级确认:`disable_plugin` 必须传 `confirm='DISABLE'`,
`uninstall_plugin` 必须传 `confirm='UNINSTALL'`。

开关完全复用现有动态插件机制:

```text
/plugins install dynamic.core management-tools-plugin-template --scope agent
/plugins enable management-tools-plugin-template --scope agent
/plugins disable management-tools-plugin-template --scope agent
```

装到 `agent` 作用域时所有 agent loop 可见;装 `management-tools-plugin-instance`
到 `agent:<id>` 时仅该 agent 可见(注册名带 `@agent-<id>` 后缀,用
`/plugins list` 查准确名字)。两种贡献共用同一模块,**二选一安装**;
LLM 也可以自己 disable 自己的管理工具(需 confirm),重新开启由 CLI/API
完成。重启后按持久化状态自动恢复。

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
