#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PYTHON_BIN=${PYTHON_BIN:-"$PROJECT_ROOT/.venv/bin/python"}
DIST_DIR=${DIST_DIR:-"$PROJECT_ROOT/dist"}
BUILD_DIR=${BUILD_DIR:-"$PROJECT_ROOT/build/packages"}
VERSION=$(
  "$PYTHON_BIN" -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])'
)

case "$(uname -s)" in
  Darwin) PLATFORM=macos ;;
  Linux) PLATFORM=linux ;;
  *) echo "Unsupported operating system: $(uname -s)" >&2; exit 1 ;;
esac

case "$(uname -m)" in
  x86_64|amd64) DEB_ARCH=amd64; RPM_ARCH=x86_64 ;;
  arm64|aarch64) DEB_ARCH=arm64; RPM_ARCH=aarch64 ;;
  *) echo "Unsupported architecture: $(uname -m)" >&2; exit 1 ;;
esac

mkdir -p "$DIST_DIR" "$BUILD_DIR"
cd "$PROJECT_ROOT"

"$PYTHON_BIN" -m PyInstaller \
  --noconfirm \
  --clean \
  --onefile \
  --name langharmess \
  --distpath "$BUILD_DIR/bin" \
  --workpath "$BUILD_DIR/pyinstaller" \
  --specpath "$BUILD_DIR" \
  --paths "$PROJECT_ROOT/src" \
  --collect-all pelix \
  --collect-all langchain_community \
  --collect-all langchain_experimental \
  --collect-data langharmess_config \
  --collect-submodules langharmess_config \
  --collect-submodules langharmess_api \
  --collect-submodules langharmess_cli \
  --collect-submodules langharmess_core \
  --collect-submodules langharmess_plugin \
  "$PROJECT_ROOT/src/langharmess_cli/__main__.py"

BINARY="$BUILD_DIR/bin/langharmess"
chmod 755 "$BINARY"

if [[ "$PLATFORM" == macos ]]; then
  MAC_ROOT="$BUILD_DIR/macos-root"
  mkdir -p "$MAC_ROOT/usr/local/bin"
  cp "$BINARY" "$MAC_ROOT/usr/local/bin/langharmess"
  xattr -cr "$MAC_ROOT"
  COPYFILE_DISABLE=1 pkgbuild \
    --root "$MAC_ROOT" \
    --identifier io.langharmess.cli \
    --version "$VERSION" \
    --install-location / \
    "$DIST_DIR/langharmess-${VERSION}-macos-$(uname -m).pkg"
  COPYFILE_DISABLE=1 tar -C "$BUILD_DIR/bin" -czf \
    "$DIST_DIR/langharmess-${VERSION}-macos-$(uname -m).tar.gz" langharmess
  exit 0
fi

if command -v dpkg-deb >/dev/null 2>&1; then
  DEB_ROOT="$BUILD_DIR/deb-root"
  mkdir -p "$DEB_ROOT/DEBIAN" "$DEB_ROOT/usr/local/bin"
  cp "$BINARY" "$DEB_ROOT/usr/local/bin/langharmess"
  cat >"$DEB_ROOT/DEBIAN/control" <<EOF
Package: langharmess
Version: $VERSION
Section: utils
Priority: optional
Architecture: $DEB_ARCH
Maintainer: langharmess
Description: Plugin-driven LangChain agent CLI
EOF
  dpkg-deb --root-owner-group --build "$DEB_ROOT" \
    "$DIST_DIR/langharmess_${VERSION}_${DEB_ARCH}.deb"
fi

if command -v rpmbuild >/dev/null 2>&1; then
  RPM_TOP="$BUILD_DIR/rpmbuild"
  mkdir -p "$RPM_TOP/BUILD" "$RPM_TOP/BUILDROOT" "$RPM_TOP/RPMS" \
    "$RPM_TOP/SOURCES" "$RPM_TOP/SPECS" "$RPM_TOP/SRPMS"
  cp "$BINARY" "$RPM_TOP/SOURCES/langharmess"
  cat >"$RPM_TOP/SPECS/langharmess.spec" <<EOF
Name: langharmess
Version: $VERSION
Release: 1%{?dist}
Summary: Plugin-driven LangChain agent CLI
License: Proprietary
BuildArch: $RPM_ARCH
Source0: langharmess

%description
Plugin-driven LangChain agent CLI with an embedded Python runtime.

%install
mkdir -p %{buildroot}/usr/local/bin
install -m 0755 %{SOURCE0} %{buildroot}/usr/local/bin/langharmess

%files
/usr/local/bin/langharmess
EOF
  rpmbuild --define "_topdir $RPM_TOP" -bb "$RPM_TOP/SPECS/langharmess.spec"
  find "$RPM_TOP/RPMS" -type f -name '*.rpm' -exec cp {} "$DIST_DIR/" \;
fi

tar -C "$BUILD_DIR/bin" -czf \
  "$DIST_DIR/langharmess-${VERSION}-linux-$(uname -m).tar.gz" langharmess
