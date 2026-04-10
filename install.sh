#!/bin/bash

# Ensure the script is run from the project directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
cd "$SCRIPT_DIR"

# Check if .env exists
if [ ! -f .env ]; then
    echo "Error: .env file not found."
    echo "Please copy .env.example to .env and configure your VAULT_PATH and GEMINI_API_KEY."
    exit 1
fi

# Load variables from .env safely, preserving spaces
while IFS='=' read -r key value; do
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
    echo "Error: VAULT_PATH is not set in .env."
    exit 1
fi

# Resolve the absolute path of the vault (eval handles ~ expansion safely here)
VAULT_ABS_PATH=$(eval echo "$VAULT_PATH")

echo "Creating Vault directory structure at: $VAULT_ABS_PATH"
mkdir -p "$VAULT_ABS_PATH/raw"
mkdir -p "$VAULT_ABS_PATH/wiki/entities"
mkdir -p "$VAULT_ABS_PATH/wiki/concepts"
mkdir -p "$VAULT_ABS_PATH/Action_Items"

# Generate the boilerplate GEMINI.md master prompt if it doesn't exist
GEMINI_MD_PATH="$VAULT_ABS_PATH/GEMINI.md"
if [ ! -f "$GEMINI_MD_PATH" ]; then
    echo "Generating boilerplate GEMINI.md..."
    cat << 'EOF' > "$GEMINI_MD_PATH"
# Role and Objective
You are an expert Python systems architect and macOS developer. We are building "Daemon.md", a fully autonomous, self-seeding knowledge graph that lives entirely inside an Obsidian markdown vault.

This system uses "Eager Compilation" rather than traditional RAG. When a user adds a raw note, a background daemon instantly uses the Gemini API to extract entities, map concepts, and write interconnected markdown files into the vault.

Your job is to plan, scaffold, and write the complete Python codebase and macOS installation scripts for this project.

# The Tech Stack
- Language: Python 3
- Libraries: `google-generativeai`, `watchdog`
- LLM Models: Gemini 3.1 Flash (for fast routing/parsing), Gemini 3.1 Pro (for deep synthesis)
- Environment: macOS (utilizing `osascript` for native push notifications and `launchd` for background services)
- Data Storage: Local Markdown files (Obsidian Vault structure)

# Vault Architecture Target
The Python scripts must assume and operate on the following directory structure (which will be located in the user's iCloud Drive):
/Daemon_Vault/
  ├── GEMINI.md (The master system prompt)
  ├── raw/ (The inbox where new `.md` files are dropped)
  ├── wiki/
  │   ├── entities/ (People, companies, hardware)
  │   └── concepts/ (Frameworks, ideas, projects)
  ├── Action_Items/ (Where executed AI tasks are saved)
  └── Maintenance_Report.md (Generated weekly)

# Core Deliverables

Please generate the code for the following three phases:

## Phase 1: The Ingestion Engine (`daemon.py`)
Write a Python script that runs continuously using the `watchdog` library.
- It must monitor the `raw/` directory.
- When a new `.md` file is detected, it reads the content and sends it to the Gemini API (`gemini-3.0-flash`).
- It MUST use Gemini's native JSON mode (`generation_config={"response_mime_type": "application/json"}`) to ensure the output never breaks the parser.
- The prompt sent to Gemini must combine the contents of `GEMINI.md` and the new raw file.
- It expects an array of JSON objects with `type` (wiki_update or task_completion), `filepath`, and `content`.
- It must write the output to the specified filepaths, appending to existing files if it's a wiki update, or overwriting if it's a task.
- It must fire a native macOS push notification (via `osascript`) summarizing what was updated.
- Finally, it should delete the raw file to clear the inbox.

## Phase 2: The Synthesis Linter (`lint_wiki.py`)
Write a secondary Python script meant to be run on a weekly cron job.
- It recursively reads every single `.md` file inside the `wiki/` directory and merges them into a single payload.
- It sends this massive payload to `gemini-3.1-pro`.
- The prompt must ask the model to audit the graph for logical contradictions, orphaned nodes, and synthesis opportunities.
- It writes the output to `Maintenance_Report.md` at the root of the vault.
- It fires a macOS push notification upon completion.

## Phase 3: The macOS Installer (`install.sh`)
Write a bash script to make this a frictionless, zero-terminal background app.
- It should dynamically generate a `com.user.daemon.md.plist` file.
- The plist should point to the user's Python path and the `daemon.py` script.
- It should move the plist to `~/Library/LaunchAgents/` and run `launchctl load` to start the daemon so it survives reboots.

# Constraints & Rules
- Do not use placeholders for API keys or paths; use `os.getenv` or a `.env` configuration file approach so the user can easily plug in their details without editing the core logic.
- Ensure all file operations handle missing directories gracefully (e.g., `os.makedirs(exist_ok=True)`).
- Write clean, heavily commented code, as this will eventually be open-sourced.
EOF
else
    echo "GEMINI.md already exists, skipping."
fi

# Find the Python executable
SYSTEM_PYTHON=$(which python3)
if [ -z "$SYSTEM_PYTHON" ]; then
    echo "Error: python3 not found."
    exit 1
fi

# Setup Python Virtual Environment
VENV_DIR="$SCRIPT_DIR/venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating Python virtual environment..."
    "$SYSTEM_PYTHON" -m venv "$VENV_DIR"
fi

# Use the venv's python and pip
PYTHON_PATH="$VENV_DIR/bin/python"
PIP_PATH="$VENV_DIR/bin/pip"

echo "Installing required Python packages..."
"$PIP_PATH" install -r "$SCRIPT_DIR/requirements.txt"

echo "Setting up Latent Space Explorer (Visualizer)..."
if [ -d "$SCRIPT_DIR/visualizer" ]; then
    cd "$SCRIPT_DIR/visualizer"
    npm install
    cd "$SCRIPT_DIR"
else
    echo "Warning: visualizer directory not found. Skipping npm install."
fi

LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$LAUNCH_AGENTS_DIR"

DAEMON_PLIST_PATH="$LAUNCH_AGENTS_DIR/com.user.daemon.md.plist"
LINTER_PLIST_PATH="$LAUNCH_AGENTS_DIR/com.user.daemon.linter.plist"

echo "Generating com.user.daemon.md.plist..."
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
    <string>$SCRIPT_DIR/daemon.err.log</string>
    <key>StandardOutPath</key>
    <string>$SCRIPT_DIR/daemon.out.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>$PATH</string>
    </dict>
</dict>
</plist>
EOF

echo "Generating com.user.daemon.linter.plist..."
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
    <string>$SCRIPT_DIR/linter.err.log</string>
    <key>StandardOutPath</key>
    <string>$SCRIPT_DIR/linter.out.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>$PATH</string>
    </dict>
</dict>
</plist>
EOF

echo "Loading plists into launchd..."
launchctl unload "$DAEMON_PLIST_PATH" 2>/dev/null || true
launchctl unload "$LINTER_PLIST_PATH" 2>/dev/null || true

launchctl load "$DAEMON_PLIST_PATH"
launchctl load "$LINTER_PLIST_PATH"

echo "Installation complete! Daemon.md is now running in the background."
echo "Logs can be found in the current directory: daemon.out.log and daemon.err.log"
