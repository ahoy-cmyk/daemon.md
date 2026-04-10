#!/bin/bash

# --- Color Constants ---
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color
BOLD='\033[1m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
cd "$SCRIPT_DIR"

echo -e "\n${BOLD}${CYAN}► Updating Daemon.md...${NC}"

# Check for uncommitted changes
if ! git diff-index --quiet HEAD --; then
    echo -e "  [${YELLOW}!${NC}] Uncommitted changes detected. Stashing..."
    git stash push -m "Auto-stash before Daemon.md update"
    STASHED=true
else
    STASHED=false
fi

echo -e "  [${CYAN}⚙${NC}] Pulling latest changes from Git..."
# Capture output to show a mini changelog
BEFORE_HASH=$(git rev-parse HEAD)
git pull --quiet
AFTER_HASH=$(git rev-parse HEAD)

if [ "$BEFORE_HASH" == "$AFTER_HASH" ]; then
    echo -e "  [${GREEN}✓${NC}] Repository is already up to date."
else
    echo -e "  [${GREEN}✓${NC}] Successfully pulled new changes."
    echo -e "\n${BOLD}Recent Commits:${NC}"
    git log --oneline "$BEFORE_HASH".."$AFTER_HASH" | while read -r line; do
        echo -e "  - ${CYAN}$line${NC}"
    done
    echo ""
fi

if [ "$STASHED" = true ]; then
    echo -e "  [${CYAN}⚙${NC}] Restoring uncommitted changes..."
    git stash pop --quiet
fi

echo -e "  [${CYAN}⚙${NC}] Delegating to installer to verify dependencies and reload services..."
# Call install.sh (which is now idempotent and fast)
./install.sh
