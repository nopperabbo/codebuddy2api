#!/bin/bash
# Install/uninstall codebuddy2api as a macOS LaunchAgent (auto-start on login)
set -e

PLIST_NAME="com.codebuddy2api.plist"
PLIST_SRC="$(cd "$(dirname "$0")" && pwd)/$PLIST_NAME"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME"
LOG_DIR="$(cd "$(dirname "$0")" && pwd)/logs"

case "${1:-install}" in
    install)
        mkdir -p "$LOG_DIR"
        mkdir -p "$HOME/Library/LaunchAgents"
        cp "$PLIST_SRC" "$PLIST_DST"
        launchctl load "$PLIST_DST"
        echo "Installed and loaded $PLIST_NAME"
        echo "Service will auto-start on login."
        echo "Logs: $LOG_DIR/"
        ;;
    uninstall)
        launchctl unload "$PLIST_DST" 2>/dev/null || true
        rm -f "$PLIST_DST"
        echo "Uninstalled $PLIST_NAME"
        ;;
    status)
        launchctl list | grep codebuddy2api || echo "Not loaded"
        ;;
    *)
        echo "Usage: $0 {install|uninstall|status}"
        exit 1
        ;;
esac
