#!/usr/bin/env bash
# Dated Notepad — uninstaller. Removes the app. YOUR NOTES ARE NEVER DELETED.
set -euo pipefail

APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/notepad"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESK="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
NOTES_DIR="$HOME/Documents/DatedNotepad"

echo "This removes the Dated Notepad app from:"
echo "  $APP_DIR"
echo "  $BIN_DIR/notepad-dated"
echo "  $DESKTOP_DIR/dated-notepad.desktop"
echo
echo "Your notes in $NOTES_DIR are KEPT."
echo "(They are plain .md files — readable in any text editor.)"
read -rp "Proceed? [y/N] " a
[[ "$a" =~ ^[Yy]$ ]] || { echo "Cancelled."; exit 0; }

rm -rf "$APP_DIR"
rm -f  "$BIN_DIR/notepad-dated"
rm -f  "$DESKTOP_DIR/dated-notepad.desktop"
rm -f  "$DESK/Dated Notepad.desktop"
ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor"
find "$ICON_DIR" -name 'dated-notepad.png' -o -name 'dated-notepad.svg' 2>/dev/null | while read -r i; do rm -f "$i"; done
command -v gtk-update-icon-cache >/dev/null 2>&1 \
  && gtk-update-icon-cache -f -t "$ICON_DIR" 2>/dev/null || true
command -v update-desktop-database >/dev/null 2>&1 \
  && update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
echo "Removed. Notes left in $NOTES_DIR"
