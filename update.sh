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

# --- Automatic GEMINI.md Update Check ---
# Check if .env exists so we can safely source it
if [ -f .env ]; then
    # Load variables from .env safely
    while IFS='=' read -r key value || [ -n "$key" ]; do
        if [[ $key == \#* ]] || [ -z "$key" ]; then continue; fi
        value="${value%\"}"
        value="${value#\"}"
        export "$key"="$value"
    done < .env

    if [ -n "$VAULT_PATH" ]; then
        VAULT_ABS_PATH="${VAULT_PATH/#\~/$HOME}"
        GEMINI_MD_PATH="$VAULT_ABS_PATH/GEMINI.md"

        if [ -f "$GEMINI_MD_PATH" ] && [ -f "$SCRIPT_DIR/known_gemini_hashes.txt" ]; then
            # Determine correct sha256 checksum command (shasum on macOS, sha256sum on Linux)
            if command -v shasum >/dev/null 2>&1; then
                CURRENT_USER_HASH=$(shasum -a 256 "$GEMINI_MD_PATH" | awk '{print $1}')
            elif command -v sha256sum >/dev/null 2>&1; then
                CURRENT_USER_HASH=$(sha256sum "$GEMINI_MD_PATH" | awk '{print $1}')
            else
                CURRENT_USER_HASH=""
            fi

            # Check if their current hash is in our list of known stock hashes
            if [ -n "$CURRENT_USER_HASH" ] && grep -q "^$CURRENT_USER_HASH\$" "$SCRIPT_DIR/known_gemini_hashes.txt"; then
                echo -e "  [${CYAN}⚙${NC}] Detected stock GEMINI.md. Updating to the latest template..."
                if cp "$SCRIPT_DIR/GEMINI.template.md" "$GEMINI_MD_PATH"; then
                    echo -e "  [${GREEN}✓${NC}] GEMINI.md updated successfully."
                else
                    echo -e "  [${YELLOW}!${NC}] Failed to update GEMINI.md. Please check file permissions."
                fi
            elif [ -n "$CURRENT_USER_HASH" ]; then
                echo -e "  [${YELLOW}!${NC}] Custom GEMINI.md detected. Skipping automatic prompt update."
            fi
        fi
    fi
fi
