#!/usr/bin/env bash
# Removes the Mirage app files. Your profile, posts and messages in ~/.local/share/mirage are kept
# unless you pass --purge.
set -euo pipefail
PREFIX="${PREFIX:-$HOME/.local}"
APP_ID="org.ubsr.Mirage"
rm -rf "$PREFIX/share/mirage/mirage" "$PREFIX/share/mirage/venv"
rm -f "$PREFIX/bin/mirage" "$PREFIX/share/applications/$APP_ID.desktop" \
      "$PREFIX/share/icons/hicolor/scalable/apps/$APP_ID.svg"
if [ "${1:-}" = "--purge" ]; then
  rm -rf "$PREFIX/share/mirage" "${XDG_CONFIG_HOME:-$HOME/.config}/mirage"
  echo "Removed Mirage and all of its data."
else
  echo "Removed Mirage. Your data is still in $PREFIX/share/mirage (use --purge to delete it too)."
fi
