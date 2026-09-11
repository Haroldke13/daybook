#!/usr/bin/env bash
# Dated Notepad — installer
# Installs to the current user's home. No root, no system packages.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/notepad"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
NOTES_DIR="$HOME/Documents/DatedNotepad"

say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; exit 1; }

say "Checking requirements"
command -v python3 >/dev/null 2>&1 || die "python3 is required but not installed."
PYV=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,8) else 1)' \
  || die "python3 >= 3.8 required (found $PYV)."
echo "    python3 $PYV — ok (standard library only, nothing to pip install)"

BROWSER=""
for c in google-chrome google-chrome-stable chromium chromium-browser brave-browser microsoft-edge; do
  if command -v "$c" >/dev/null 2>&1; then BROWSER="$c"; break; fi
done
if [ -n "$BROWSER" ]; then
  echo "    browser: $BROWSER — ok"
else
  warn "No Chrome/Chromium found. Install one, or use 'notepad-dated --serve'."
fi

say "Installing to $APP_DIR"
mkdir -p "$APP_DIR/static" "$BIN_DIR" "$DESKTOP_DIR"
install -m 0644 "$SRC/app/server.py"         "$APP_DIR/server.py"
install -m 0644 "$SRC/app/static/index.html" "$APP_DIR/static/index.html"
install -m 0755 "$SRC/app/notepad-dated"     "$BIN_DIR/notepad-dated"

say "Preparing notes directory"
if [ -d "$NOTES_DIR" ] && [ -n "$(ls -A "$NOTES_DIR" 2>/dev/null)" ]; then
  echo "    $NOTES_DIR already exists with notes in it — left untouched."
else
  mkdir -p "$NOTES_DIR"
  echo "    created $NOTES_DIR"
fi

install -m 0755 "$SRC/app/set-window-icon.sh" "$APP_DIR/set-window-icon.sh"
install -m 0644 "$SRC/app/icon-wm.dat"        "$APP_DIR/icon-wm.dat"

say "Installing icons"
ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor"
if [ -d "$SRC/icons/hicolor" ]; then
  ( cd "$SRC/icons/hicolor" && find . -type f \( -name '*.png' -o -name '*.svg' \) -print0 \
    | while IFS= read -r -d '' f; do
        mkdir -p "$ICON_DIR/$(dirname "$f")"
        install -m 0644 "$f" "$ICON_DIR/$f"
      done )
  command -v gtk-update-icon-cache >/dev/null 2>&1 \
    && gtk-update-icon-cache -f -t "$ICON_DIR" 2>/dev/null || true
  echo "    app icon installed (SVG + 8 PNG sizes)"
else
  warn "icons/ directory missing — the app will fall back to a generic icon."
fi

say "Creating desktop entry"
sed -e "s|@EXEC@|$BIN_DIR/notepad-dated|g" "$SRC/desktop/dated-notepad.desktop.in" \
  > "$DESKTOP_DIR/dated-notepad.desktop"
chmod 0644 "$DESKTOP_DIR/dated-notepad.desktop"
command -v update-desktop-database >/dev/null 2>&1 \
  && update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

DESK="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
if [ -d "$DESK" ]; then
  cp "$DESKTOP_DIR/dated-notepad.desktop" "$DESK/Dated Notepad.desktop"
  chmod +x "$DESK/Dated Notepad.desktop"
  gio set "$DESK/Dated Notepad.desktop" metadata::trusted true 2>/dev/null || true
  echo "    shortcut placed on $DESK"
fi

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) warn "$BIN_DIR is not on your PATH. Add to ~/.bashrc:"
     warn "    export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac

cat <<DONE

  Dated Notepad installed.

    Launch:      notepad-dated
    Or:          your app menu -> "Dated Notepad"
    Your notes:  $NOTES_DIR  (one plain .md file per day)
    No browser:  notepad-dated --serve
    Remove:      ./uninstall.sh   (your notes are kept)

DONE
