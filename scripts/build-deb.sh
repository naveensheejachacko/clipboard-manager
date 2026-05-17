#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(grep -E '^version\s*=' "${ROOT}/pyproject.toml" | head -1 | sed -E 's/^version\s*=\s*"([^"]+)".*/\1/')"
PKG="clipboard-manager_${VERSION}_all"
STAGE="${ROOT}/dist/${PKG}"
CTRL="${STAGE}/DEBIAN/control"

rm -rf "${STAGE}"
mkdir -p "${STAGE}/DEBIAN"
mkdir -p "${STAGE}/usr/lib/python3/dist-packages"
mkdir -p "${STAGE}/usr/bin"
mkdir -p "${STAGE}/usr/share/applications"
mkdir -p "${STAGE}/etc/xdg/autostart"
mkdir -p "${STAGE}/usr/share/icons/hicolor/scalable/apps"
mkdir -p "${STAGE}/usr/share/icons/hicolor/symbolic/status"
mkdir -p "${STAGE}/usr/lib/python3/dist-packages/winclip/data/icons/hicolor/scalable/apps"
mkdir -p "${STAGE}/usr/lib/python3/dist-packages/winclip/data/icons/hicolor/symbolic/status"

cp -a "${ROOT}/src/winclip" "${STAGE}/usr/lib/python3/dist-packages/"
rm -rf "${STAGE}/usr/lib/python3/dist-packages/winclip/__pycache__"
find "${STAGE}/usr/lib/python3/dist-packages/winclip" -maxdepth 3 -type f -name '*.pyc' -delete 2>/dev/null || true

cat >"${STAGE}/usr/bin/clipboard-manager" <<'EOF'
#!/bin/sh
exec python3 -m winclip "$@"
EOF
chmod 0755 "${STAGE}/usr/bin/clipboard-manager"
ln -sf clipboard-manager "${STAGE}/usr/bin/winclip"

cp "${ROOT}/resources/clipboard-manager.desktop" \
  "${STAGE}/usr/share/applications/clipboard-manager.desktop"
cp "${ROOT}/resources/clipboard-manager-autostart.desktop" \
  "${STAGE}/etc/xdg/autostart/clipboard-manager.desktop"

ICON_SRC="${ROOT}/resources/icons/hicolor"
cp "${ICON_SRC}/scalable/apps/clipboard-manager.svg" \
  "${STAGE}/usr/share/icons/hicolor/scalable/apps/clipboard-manager.svg"
cp "${ICON_SRC}/symbolic/status/clipboard-manager-symbolic.svg" \
  "${STAGE}/usr/share/icons/hicolor/symbolic/status/clipboard-manager-symbolic.svg"
cp "${ICON_SRC}/scalable/apps/clipboard-manager.svg" \
  "${STAGE}/usr/lib/python3/dist-packages/winclip/data/icons/hicolor/scalable/apps/clipboard-manager.svg"
cp "${ICON_SRC}/symbolic/status/clipboard-manager-symbolic.svg" \
  "${STAGE}/usr/lib/python3/dist-packages/winclip/data/icons/hicolor/symbolic/status/clipboard-manager-symbolic.svg"

cat >"${CTRL}" <<EOF
Package: clipboard-manager
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: all
Maintainer: Clipboard Manager <local@localhost>
Standards-Version: 4.6.2
Provides: winclip
Replaces: winclip
Conflicts: winclip
Depends: python3 (>= 3.8), python3-gi, gir1.2-gtk-3.0, gir1.2-gdkpixbuf-2.0
Recommends: python3-pynput, gir1.2-ayatanaappindicator3-0.1, xclip, wl-clipboard
Description: Clipboard Manager — history for Linux (GTK)
 Clipboard Manager keeps a rolling history of text and file paths,
 with search, pinning, and tray icon. Bind a shortcut to
 clipboard-manager --toggle (Win+V style on Linux Mint / Ubuntu).
EOF

chmod 0644 "${STAGE}/DEBIAN/control"

cat >"${STAGE}/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
case "$1" in
  configure|abort-upgrade|abort-deconfigure|abort-remove)
    if command -v update-desktop-database >/dev/null 2>&1; then
      update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
      gtk-update-icon-cache -f /usr/share/icons/hicolor >/dev/null 2>&1 || true
    fi
    ;;
esac
exit 0
EOF

cat >"${STAGE}/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
case "$1" in
  remove|purge|abort-install|abort-upgrade)
    if command -v update-desktop-database >/dev/null 2>&1; then
      update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
      gtk-update-icon-cache -f /usr/share/icons/hicolor >/dev/null 2>&1 || true
    fi
    ;;
esac
exit 0
EOF

chmod 0755 "${STAGE}/DEBIAN/postinst" "${STAGE}/DEBIAN/postrm"

fakeroot dpkg-deb --build "${STAGE}" "${ROOT}/dist/${PKG}.deb"

echo "Built ${ROOT}/dist/${PKG}.deb"
