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

The default configuration is created at `~/.langharmess/langharmess.ini`:

```ini
[DEFAULT]
log_file = ~/.langharmess/langharmess.log

[providers.deepseek-v4-flash]
base_url = xxxxx
model = xxxxx
api_key = xxxx
```

Select a configured model provider and optionally override the log destination:

```bash
langharmess --provider deepseek-v4-flash --log ~/.langharmess/debug.log
```

`LANG_HARMESS_CONFIG` can override the INI file location. Existing
`LANG_HARMESS_MODEL`, `LANG_HARMESS_API_KEY`, and `LANG_HARMESS_BASE_URL`
values remain the fallback when `--provider` is omitted.
