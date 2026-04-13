#!/bin/bash

# --- Color Constants ---
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color
BOLD='\033[1m'

echo -e "\n${BOLD}${CYAN}Initializing Daemon.md Setup...${NC}\n"

# Ensure the script is run from the project directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
cd "$SCRIPT_DIR"

# Check if .env exists
if [ ! -f .env ]; then
    echo -e "${RED}[✗] Error: .env file not found.${NC}"
    echo -e "Please copy .env.example to .env and configure your VAULT_PATH and GEMINI_API_KEY."
    exit 1
fi

# Load variables from .env safely, preserving spaces
while IFS='=' read -r key value || [ -n "$key" ]; do
    # Skip comments and empty lines
    if [[ $key == \#* ]] || [ -z "$key" ]; then
        continue
    fi
    # Remove surrounding quotes from the value if they exist
    value="${value%\"}"
    value="${value#\"}"
    export "$key"="$value"
done < .env

if [ -z "$VAULT_PATH" ]; then
    echo -e "${RED}[✗] Error: VAULT_PATH is not set in .env.${NC}"
    exit 1
fi

# Resolve the absolute path of the vault securely (preventing command injection)
VAULT_ABS_PATH="${VAULT_PATH/#\~/$HOME}"

# Test read/write permissions (crucial for iCloud paths and macOS FDA)
if ! touch "$VAULT_ABS_PATH/.daemon_test_write" 2>/dev/null; then
    echo -e "${RED}[✗] Permission Denied: Cannot write to $VAULT_ABS_PATH${NC}"
    echo -e "${YELLOW}macOS explicitly protects iCloud and Desktop paths. You must grant your Terminal app 'Full Disk Access' in System Settings > Privacy & Security.${NC}"
    exit 1
fi
rm -f "$VAULT_ABS_PATH/.daemon_test_write"

echo -e "  [${GREEN}✓${NC}] Path Permissions Verified"

echo -e "  [${CYAN}⚙${NC}] Scaffolding Vault directory structure..."
mkdir -p "$VAULT_ABS_PATH/raw"
mkdir -p "$VAULT_ABS_PATH/failed"
mkdir -p "$VAULT_ABS_PATH/archive"
mkdir -p "$VAULT_ABS_PATH/wiki/entities"
mkdir -p "$VAULT_ABS_PATH/wiki/concepts"
mkdir -p "$VAULT_ABS_PATH/Action_Items"

# Generate the boilerplate GEMINI.md master prompt if it doesn't exist
GEMINI_MD_PATH="$VAULT_ABS_PATH/GEMINI.md"

if [ ! -e "$GEMINI_MD_PATH" ]; then
    echo -e "  [${CYAN}⚙${NC}] Copying comprehensive GEMINI.md master prompt from template..."
    cp "$SCRIPT_DIR/GEMINI.template.md" "$GEMINI_MD_PATH"
else
    echo -e "  [${GREEN}✓${NC}] GEMINI.md already exists, skipping generation."
fi

echo -e "\n${BOLD}${CYAN}Resolving Dependencies...${NC}"

# Check for core dependencies
SYSTEM_PYTHON=$(command -v python3)
if [ -z "$SYSTEM_PYTHON" ]; then
    echo -e "${RED}[✗] Error: python3 is not installed or not in PATH.${NC}"
    exit 1
fi

if ! command -v npm &> /dev/null; then
    echo -e "${RED}[✗] Error: npm is not installed or not in PATH.${NC}"
    exit 1
fi

echo -e "  [${GREEN}✓${NC}] python3 and npm found in PATH."

# --- Python Dependencies with Hash Caching ---
VENV_DIR="$SCRIPT_DIR/venv"
PY_HASH_FILE="$VENV_DIR/.req_hash"

if [ ! -d "$VENV_DIR" ]; then
    echo -e "  [${CYAN}⚙${NC}] Creating Python virtual environment..."
    "$SYSTEM_PYTHON" -m venv "$VENV_DIR"
fi

PYTHON_PATH="$VENV_DIR/bin/python"
PIP_PATH="$VENV_DIR/bin/pip"

# Check if requirements.txt has changed
CURRENT_REQ_HASH=$(shasum "$SCRIPT_DIR/requirements.txt" | awk '{print $1}')
if [ -f "$PY_HASH_FILE" ] && [ "$(cat "$PY_HASH_FILE")" == "$CURRENT_REQ_HASH" ]; then
    echo -e "  [${GREEN}✓${NC}] Python dependencies up to date (cached)."
else
    echo -e "  [${CYAN}⚙${NC}] Installing/Updating Python packages..."
    "$PIP_PATH" install -q -r "$SCRIPT_DIR/requirements.txt"
    echo "$CURRENT_REQ_HASH" > "$PY_HASH_FILE"
fi

# --- NPM Dependencies with Hash Caching ---
if [ -d "$SCRIPT_DIR/visualizer" ]; then
    NPM_HASH_FILE="$SCRIPT_DIR/visualizer/node_modules/.pkg_hash"
    CURRENT_NPM_HASH=$(shasum "$SCRIPT_DIR/visualizer/package.json" | awk '{print $1}')

    if [ -f "$NPM_HASH_FILE" ] && [ "$(cat "$NPM_HASH_FILE")" == "$CURRENT_NPM_HASH" ]; then
        echo -e "  [${GREEN}✓${NC}] Visualizer NPM dependencies up to date (cached)."
    else
        echo -e "  [${CYAN}⚙${NC}] Installing/Updating Latent Space Explorer dependencies (npm)..."
        cd "$SCRIPT_DIR/visualizer"
        npm install --silent
        echo "$CURRENT_NPM_HASH" > "node_modules/.pkg_hash"
        cd "$SCRIPT_DIR"
    fi
else
    echo -e "  [${YELLOW}!${NC}] Warning: visualizer directory not found. Skipping npm install."
fi

# Setup centralized logging
LOGS_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOGS_DIR"

echo -e "\n${BOLD}${CYAN}Configuring macOS launchd Background Services...${NC}"

LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$LAUNCH_AGENTS_DIR"

DAEMON_PLIST_PATH="$LAUNCH_AGENTS_DIR/com.user.daemon.md.plist"
LINTER_PLIST_PATH="$LAUNCH_AGENTS_DIR/com.user.daemon.linter.plist"

echo -e "  [${CYAN}⚙${NC}] Generating com.user.daemon.md.plist..."
cat << EOF > "$DAEMON_PLIST_PATH"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.user.daemon.md</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_PATH</string>
        <string>$SCRIPT_DIR/daemon.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$SCRIPT_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardErrorPath</key>
    <string>$LOGS_DIR/daemon.launchd.err.log</string>
    <key>StandardOutPath</key>
    <string>$LOGS_DIR/daemon.launchd.out.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>$PATH</string>
    </dict>
</dict>
</plist>
EOF

echo -e "  [${CYAN}⚙${NC}] Generating com.user.daemon.linter.plist..."
cat << EOF > "$LINTER_PLIST_PATH"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.user.daemon.linter</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_PATH</string>
        <string>$SCRIPT_DIR/lint_wiki.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$SCRIPT_DIR</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key>
        <integer>0</integer> <!-- Sunday -->
        <key>Hour</key>
        <integer>3</integer> <!-- 3 AM -->
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardErrorPath</key>
    <string>$LOGS_DIR/linter.launchd.err.log</string>
    <key>StandardOutPath</key>
    <string>$LOGS_DIR/linter.launchd.out.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>$PATH</string>
    </dict>
</dict>
</plist>
EOF

echo -e "  [${CYAN}⚙${NC}] Loading plists into launchd..."
launchctl unload "$DAEMON_PLIST_PATH" 2>/dev/null || true
launchctl unload "$LINTER_PLIST_PATH" 2>/dev/null || true

launchctl load "$DAEMON_PLIST_PATH"
launchctl load "$LINTER_PLIST_PATH"

echo -e "  [${GREEN}✓${NC}] Services successfully loaded."

echo -e "\n${BOLD}${GREEN}================================================${NC}"
echo -e "${BOLD}${GREEN}✓ Installation complete. Background services active.${NC}"
echo -e "${BOLD}${GREEN}================================================${NC}"
echo -e "\n${BOLD}Next Steps:${NC}"
echo -e "  1. Drop a markdown note into: ${CYAN}$VAULT_ABS_PATH/raw/${NC}"
echo -e "  2. Execute ${YELLOW}./status.sh${NC} to monitor token usage."
echo -e "  3. Execute ${YELLOW}./start_visualizer.sh${NC} to render the 3D topology."
echo -e "\nLogs are routed to the ${CYAN}logs/${NC} directory.\n"
