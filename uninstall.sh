#!/bin/bash

echo "Uninstalling Daemon.md background services..."

LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
DAEMON_PLIST_PATH="$LAUNCH_AGENTS_DIR/com.user.daemon.md.plist"
LINTER_PLIST_PATH="$LAUNCH_AGENTS_DIR/com.user.daemon.linter.plist"

# Unload services
launchctl unload "$DAEMON_PLIST_PATH" 2>/dev/null || true
launchctl unload "$LINTER_PLIST_PATH" 2>/dev/null || true

# Remove plists
rm -f "$DAEMON_PLIST_PATH"
rm -f "$LINTER_PLIST_PATH"

echo "Background services removed."
echo "Note: Your Obsidian Vault contents and Python scripts have NOT been deleted."
