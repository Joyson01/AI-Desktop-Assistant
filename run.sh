#!/usr/bin/env bash
# Prevent Snap VS Code from leaking mismatched GLib/GSettings schemas into subprocesses
unset GSETTINGS_SCHEMA_DIR

if [ -n "$XDG_DATA_DIRS" ]; then
    CLEANED_DIRS=$(echo "$XDG_DATA_DIRS" | tr ':' '\n' | grep -v 'snap/code' | paste -sd ':' -)
    export XDG_DATA_DIRS="${CLEANED_DIRS:-/usr/local/share/:/usr/share/:/var/lib/snapd/desktop}"
fi

export QT_QPA_PLATFORMTHEME="${QT_QPA_PLATFORMTHEME:-xdgdesktopportal}"
export QT_STYLE_OVERRIDE="${QT_STYLE_OVERRIDE:-Fusion}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/ai/voice_desktop_ai/run.sh" "$@"
