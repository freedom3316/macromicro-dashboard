#!/usr/bin/env zsh
set -euo pipefail

LABEL="com.freedom33.truthsocial.monitor"
PLIST_SRC="/Users/freedom33/Documents/New_project/launchd/com.freedom33.truthsocial.monitor.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$LABEL.plist"

mkdir -p "$HOME/Library/LaunchAgents"
cp "$PLIST_SRC" "$PLIST_DST"

launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DST"
launchctl enable "gui/$(id -u)/$LABEL"
launchctl kickstart -k "gui/$(id -u)/$LABEL"

echo "Installed and started: $LABEL"
launchctl print "gui/$(id -u)/$LABEL" | head -n 40
