#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <langharmess.pkg|langharmess.deb|langharmess.rpm|tar.gz>" >&2
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
    sudo install -m 0755 "$INSTALL_TMP/langharmess" /usr/local/bin/langharmess
    ;;
  *)
    echo "Unsupported package: $ARTIFACT" >&2
    exit 2
    ;;
esac

CONFIG_DIR=${LANG_HARMESS_HOME:-"$HOME/.langharmess"}
CONFIG_FILE="$CONFIG_DIR/langharmess.toml"
mkdir -p "$CONFIG_DIR"
if [[ ! -f "$CONFIG_FILE" ]]; then
  cat >"$CONFIG_FILE" <<'EOF'
[DEFAULT]

[plugins.ui]
builtin_package="langharmess_cli.plugin:builtin_package"
sdk_package="langharmess_api.sdk:package"

[plugins.server]
builtin_package="langharmess_api.plugin:builtin_package"

[plugins.agent]
builtin_package="langharmess_core.plugin:builtin_package"

[plugins.log]
builtin_package="langharmess_logging.plugin:builtin_package"

# Default model used when interactive mode starts without --provider.
# [providers.default]
# protocol="chat"
# base_url="https://api.example.com/v1"
# model="your-model"
# api_key="your-api-key"
EOF
fi

echo "Installed: $(command -v langharmess)"
echo "Config: $CONFIG_FILE"
langharmess --help
