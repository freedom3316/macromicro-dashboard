#!/usr/bin/env zsh
set -euo pipefail

LABEL="com.freedom33.truthsocial.monitor"
PLIST_DST="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
rm -f "$PLIST_DST"

echo "Uninstalled: $LABEL"
