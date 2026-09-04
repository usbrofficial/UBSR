#!/usr/bin/env bash
# Installs Mirage for the current user on Zorin OS 17+ (also Ubuntu 22.04+/Debian 12+).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${PREFIX:-$HOME/.local}"
APP_DIR="$PREFIX/share/mirage"
BIN_DIR="$PREFIX/bin"
APP_ID="org.ubsr.Mirage"

say() { printf '\033[1;35m[mirage]\033[0m %s\n' "$*"; }

if ! command -v apt-get >/dev/null 2>&1; then
  say "This installer targets Debian/Ubuntu based systems such as Zorin OS. Install GTK 4, libadwaita and PyGObject with your package manager, then run ./run.sh."
  exit 1
fi

say "Installing system packages (GTK 4, libadwaita, PyGObject)…"
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-venv python3-pip python3-gi python3-gi-cairo \
  gir1.2-gtk-4.0 gir1.2-adw-1 libadwaita-1-0 gir1.2-gdkpixbuf-2.0

if ! python3 -c 'import gi; gi.require_version("Gtk","4.0"); gi.require_version("Adw","1"); from gi.repository import Gtk, Adw' 2>/dev/null; then
  say "GTK 4 / libadwaita bindings are not importable. Mirage needs Zorin OS 17 or newer (Ubuntu 22.04+)."
  exit 1
fi

say "Copying the app to $APP_DIR…"
mkdir -p "$APP_DIR" "$BIN_DIR"
rm -rf "$APP_DIR/mirage"
cp -r "$HERE/mirage" "$APP_DIR/mirage"
find "$APP_DIR/mirage" -name '__pycache__' -type d -prune -exec rm -rf {} +

say "Creating a virtual environment with the Anthropic SDK…"
if [ ! -x "$APP_DIR/venv/bin/python" ]; then
  python3 -m venv --system-site-packages "$APP_DIR/venv"
fi
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/venv/bin/pip" install --quiet -r "$HERE/requirements.txt"

say "Writing launcher $BIN_DIR/mirage…"
cat > "$BIN_DIR/mirage" <<LAUNCHER
#!/usr/bin/env bash
export PYTHONPATH="$APP_DIR\${PYTHONPATH:+:\$PYTHONPATH}"
exec "$APP_DIR/venv/bin/python" -m mirage "\$@"
LAUNCHER
chmod +x "$BIN_DIR/mirage"

say "Installing desktop entry and icon…"
mkdir -p "$PREFIX/share/applications" "$PREFIX/share/icons/hicolor/scalable/apps"
sed "s|^Exec=.*|Exec=$BIN_DIR/mirage|" "$HERE/mirage/data/$APP_ID.desktop" > "$PREFIX/share/applications/$APP_ID.desktop"
cp "$HERE/mirage/data/icons/$APP_ID.svg" "$PREFIX/share/icons/hicolor/scalable/apps/$APP_ID.svg"
update-desktop-database "$PREFIX/share/applications" 2>/dev/null || true
gtk-update-icon-cache -q -t "$PREFIX/share/icons/hicolor" 2>/dev/null || true

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) say "Note: $BIN_DIR is not on your PATH yet; log out and back in, or run $BIN_DIR/mirage directly." ;;
esac

say "Done. Launch Mirage from the app menu, or run: mirage"
