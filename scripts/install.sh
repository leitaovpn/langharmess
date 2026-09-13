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
CONFIG_FILE="$CONFIG_DIR/langharmess.ini"
mkdir -p "$CONFIG_DIR"
if [[ ! -f "$CONFIG_FILE" ]]; then
  cat >"$CONFIG_FILE" <<'EOF'
[DEFAULT]

log_file = ~/.langharmess/langharmess.log

[providers.deepseek-v4-flash]

base_url=xxxxx

model=xxxxx

api_key=xxxx
EOF
fi

echo "Installed: $(command -v langharmess)"
echo "Config: $CONFIG_FILE"
langharmess --help
