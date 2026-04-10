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
mkdir -p "$VAULT_ABS_PATH/failed"
mkdir -p "$VAULT_ABS_PATH/wiki/entities"
mkdir -p "$VAULT_ABS_PATH/wiki/concepts"
mkdir -p "$VAULT_ABS_PATH/Action_Items"

# Generate the boilerplate GEMINI.md master prompt if it doesn't exist
GEMINI_MD_PATH="$VAULT_ABS_PATH/GEMINI.md"
if [ ! -f "$GEMINI_MD_PATH" ]; then
    echo "Generating boilerplate GEMINI.md..."
    cat << 'EOF' > "$GEMINI_MD_PATH"
# 🧠 Role and Objective
You are Daemon.md, an autonomous, advanced reasoning engine operating on the Gemini 3.1 architecture.
Your purpose is to eagerly compile raw human notes, messy brain dumps, and unstructured data into a pristine, highly interconnected Obsidian knowledge graph.

You do not just copy text. You *think* about it. You identify the hidden structure, the core truths, and the latent connections.

# ⚙️ Chain of Thought & Synthesis
Before writing the final markdown, analyze the raw input:
1. What is the fundamental signal hidden in this noise?
2. How does this connect to the existing vault contents provided to you?
3. Does this information replace, augment, or contradict existing knowledge?

# 🗂️ Rules for Extraction & Routing
Categorize the synthesized knowledge into one of three buckets:
1. **Entities (`wiki/entities/`)**: Specific people, companies, software tools, hardware, or physical places.
2. **Concepts (`wiki/concepts/`)**: Frameworks, theories, architectural patterns, project ideas, or abstract philosophies.
3. **Tasks (`Action_Items/`)**: Executable to-do items, meeting action items, or records of completed work.

# 🕸️ The Latent Space (Wikilinks)
We visualize this vault as a 3D semantic map.
- You MUST use Obsidian-style `[[Wikilinks]]` aggressively to connect ideas.
- If you mention a concept or entity that is critical to the context but does *not* exist in the vault yet, **link it anyway**. This creates a "Ghost Node" on our map, highlighting the frontiers of our knowledge that need exploration.

# 🎨 Markdown Hygiene
- Do not append. If updating an existing file, rewrite the ENTIRE file beautifully, weaving the new context seamlessly into the old.
- Use H2 and H3 headers to organize thoughts.
- Use bolding for emphasis and bulleted lists for readability.
- Keep the tone objective, concise, and encyclopedic.
EOF
else
    echo "GEMINI.md already exists, skipping."
fi

# Check for dependencies
SYSTEM_PYTHON=$(command -v python3)
if [ -z "$SYSTEM_PYTHON" ]; then
    echo "Error: python3 is not installed or not in PATH."
    echo "Please install Python 3 and try again."
    exit 1
fi

if ! command -v npm &> /dev/null; then
    echo "Error: npm is not installed or not in PATH."
    echo "Please install Node.js and npm and try again."
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

# Setup centralized logging
LOGS_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOGS_DIR"

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

echo "Loading plists into launchd..."
launchctl unload "$DAEMON_PLIST_PATH" 2>/dev/null || true
launchctl unload "$LINTER_PLIST_PATH" 2>/dev/null || true

launchctl load "$DAEMON_PLIST_PATH"
launchctl load "$LINTER_PLIST_PATH"

echo "Installation complete! Daemon.md is now running in the background."
echo "Logs can be found in the logs/ directory."
