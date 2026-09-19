#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <langharness.pkg|langharness.deb|langharness.rpm|tar.gz>" >&2
  exit 2
fi

ARTIFACT=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
case "$ARTIFACT" in
  *.pkg)
    sudo installer -pkg "$ARTIFACT" -target /
    ;;
  *.deb)
    sudo dpkg -i "$ARTIFACT"
    ;;
  *.rpm)
    sudo rpm -Uvh --replacepkgs "$ARTIFACT"
    ;;
  *.tar.gz)
    INSTALL_TMP=$(mktemp -d)
    tar -xzf "$ARTIFACT" -C "$INSTALL_TMP"
    sudo install -m 0755 "$INSTALL_TMP/langharness" /usr/local/bin/langharness
    ;;
  *)
    echo "Unsupported package: $ARTIFACT" >&2
    exit 2
    ;;
esac

CONFIG_DIR=${LANG_HARNESS_HOME:-"$HOME/.langharness"}
CONFIG_FILE="$CONFIG_DIR/langharness.toml"
mkdir -p "$CONFIG_DIR"
if [[ ! -f "$CONFIG_FILE" ]]; then
  cat >"$CONFIG_FILE" <<'EOF'
[DEFAULT]

[plugins.ui]
builtin_package="langharness_cli.plugin:builtin_package"
sdk_package="langharness_api.sdk:package"

[plugins.server]
builtin_package="langharness_api.plugin:builtin_package"

[plugins.agent]
builtin_package="langharness_core.plugin:builtin_package"

[plugins.log]
builtin_package="langharness_logging.plugin:builtin_package"

# Default model used when interactive mode starts without --provider.
# [providers.default]
# protocol="chat"
# base_url="https://api.example.com/v1"
# model="your-model"
# api_key="your-api-key"
EOF
fi

echo "Installed: $(command -v langharness)"
echo "Config: $CONFIG_FILE"
langharness --help
