#!/usr/bin/env bash
# Removes the UBSR app files. Your profile, posts and messages in ~/.local/share/ubsr are kept
# unless you pass --purge.
set -euo pipefail
PREFIX="${PREFIX:-$HOME/.local}"
APP_ID="org.ubsr.UBSR"
rm -rf "$PREFIX/share/ubsr/ubsr" "$PREFIX/share/ubsr/venv"
rm -f "$PREFIX/bin/ubsr" "$PREFIX/share/applications/$APP_ID.desktop" \
      "$PREFIX/share/icons/hicolor/scalable/apps/$APP_ID.svg"
if [ "${1:-}" = "--purge" ]; then
  rm -rf "$PREFIX/share/ubsr" "${XDG_CONFIG_HOME:-$HOME/.config}/ubsr"
  echo "Removed UBSR and all of its data."
else
  echo "Removed UBSR. Your data is still in $PREFIX/share/ubsr (use --purge to delete it too)."
fi
