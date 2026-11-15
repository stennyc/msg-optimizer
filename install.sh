#!/usr/bin/env bash
# install.sh - msg-optimizer plugin installer
# Supports both Linux and Windows (via git-bash/MSYS).
#
# Usage:
#   bash install.sh [--profile <name>] [--all-profiles] [--dry-run]
#
# Platforms:
#   Linux:  $HERMES_HOME/plugins/msg-optimizer  (default: ~/.hermes/plugins/msg-optimizer)
#   Windows: C:/Users/<user>/AppData/Local/hermes/plugins/msg-optimizer
#            AND  ~/.hermes/plugins/msg-optimizer  (dual-install)
set -euo pipefail

DRY_RUN=false
PROFILE=""
ALL_PROFILES=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)      DRY_RUN=true; shift ;;
    --profile)      PROFILE="$2"; shift 2 ;;
    --all-profiles) ALL_PROFILES=true; shift ;;
    *) echo "unknown arg: $1"; exit 2 ;;
  esac
done

HERMES_HOME="${{HERMES_HOME:-$HOME/.hermes}}"
SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
PLUGIN_NAME="msg-optimizer"

if command -v cygpath >/dev/null 2>&1; then
  PLUGINS_DIR_WIN="C:/Users/$(whoami)/AppData/Local/hermes/plugins"
else
  PLUGINS_DIR_WIN=""
fi

install_to() {{
  local dest="$1" label="$2"
  if [ "$DRY_RUN" = true ]; then
    echo "  [dry-run] would install msg-optimizer to $label: $dest"
    return 0
  fi
  mkdir -p "$dest"
  cp -r "$SCRIPT_DIR/"* "$dest/" 2>/dev/null || true
  [ -d "$SCRIPT_DIR/.git" ] && [ ! -d "$dest/.git" ] && cp -r "$SCRIPT_DIR/.git" "$dest/"
  echo "  [ok] $label: $dest"
}}

echo "=== msg-optimizer installer ==="
echo "[1/3] Installing plugin source..."
install_to "$HERMES_HOME/plugins/$PLUGIN_NAME" "linux ($HERMES_HOME)"
[ -n "$PLUGINS_DIR_WIN" ] && install_to "$PLUGINS_DIR_WIN/$PLUGIN_NAME" "windows (AppData)"

echo "[2/3] Setting up profile symlinks..."
if [ -n "$PLUGINS_DIR_WIN" ]; then
  PROFILES_DIR="$PLUGINS_DIR_WIN/../profiles"
else
  PROFILES_DIR="$HERMES_HOME/profiles"
fi

if [ -d "$PROFILES_DIR" ]; then
  if [ -n "$PROFILE" ]; then
    PROFILE_LIST=("$PROFILE")
  elif [ "$ALL_PROFILES" = true ]; then
    PROFILE_LIST=($(ls "$PROFILES_DIR"))
  else
    PROFILE_LIST=()
    for d in "$PROFILES_DIR"/*/; do
      [ -d "$d" ] || continue
      n=$(basename "$d"); [[ "$n" == .* ]] && continue
      PROFILE_LIST+=("$n")
    done
  fi

  for prof in "${{PROFILE_LIST[@]}}"; do
    cfg="$PROFILES_DIR/$prof/config.yaml"
    has=false
    [ -f "$cfg" ] && grep -qE '^\s*-\s*msg-optimizer\s*$' "$cfg" 2>/dev/null && has=true
    if [ "$has" = true ]; then
      link="$PROFILES_DIR/$prof/plugins/$PLUGIN_NAME"
      src="$PLUGINS_DIR_WIN/$PLUGIN_NAME" 2>/dev/null || src="$HERMES_HOME/plugins/$PLUGIN_NAME"
      [ -f "$link" ] && rm -f "$link"
      [ -d "$link" ] && rm -rf "$link"
      if [ "$DRY_RUN" = true ]; then
        echo "  [dry-run] symlink $link -> $src"
      else
        [ -n "$PLUGINS_DIR_WIN" ] && src="$(cygpath -m "$src")"
        ln -s "$src" "$link"
        echo "  [ok] $prof/plugins/$PLUGIN_NAME -> $src"
      fi
    fi
  done
fi

echo "[3/3] Verification..."
count=0
for d in "$HERMES_HOME/plugins/$PLUGIN_NAME" "${{PLUGINS_DIR_WIN:+$PLUGINS_DIR_WIN/$PLUGIN_NAME}}"; do
  [ -n "$d" ] && [ -f "$d/__init__.py" ] && count=$((count+1))
done
echo "  installed to $count location(s)"
echo "Done. Restart the Hermes gateway for changes to take effect."
