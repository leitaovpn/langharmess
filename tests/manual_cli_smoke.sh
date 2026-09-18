#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PYTHON=${PYTHON:-"$ROOT/.venv/bin/python"}
CLI=${CLI:-"$ROOT/.venv/bin/langharmess"}
SMOKE_DIR=${SMOKE_DIR:-"$ROOT/.tmp-cli-real-smoke"}
SERVER_PORT=${SERVER_PORT:-11534}
PROVIDER=${PROVIDER:-}

if [[ -z "$PROVIDER" ]]; then
  echo "PROVIDER is required for the real LLM portion." >&2
  exit 2
fi

export LANG_HARMESS_DIR="$SMOKE_DIR"

echo "== dynamic plugin lifecycle =="
"$CLI" --dir "$SMOKE_DIR" plugins discover \
  --server-port "$SERVER_PORT" --token secret
"$CLI" --dir "$SMOKE_DIR" plugins install real.echo echo \
  --scope server --server-port "$SERVER_PORT" --token secret
"$CLI" --dir "$SMOKE_DIR" plugins disable real-echo \
  --scope server --server-port "$SERVER_PORT" --token secret
"$CLI" --dir "$SMOKE_DIR" plugins enable real-echo \
  --scope server --server-port "$SERVER_PORT" --token secret
"$CLI" --dir "$SMOKE_DIR" plugins uninstall real-echo \
  --scope server --server-port "$SERVER_PORT" --token secret

echo "== real LLM interactive flow =="
printf '%s\n' \
  'remember smoke-alpha' \
  'what did I just say?' \
  '/agents' \
  '/agent simple_agent' \
  'what did I just say?' \
  '/exit' |
  "$CLI" --dir "$SMOKE_DIR" --provider "$PROVIDER" interactive \
    --server-port "$SERVER_PORT" \
    --token secret \
    --user-id smoke_user \
    --agent-id simple_agent
