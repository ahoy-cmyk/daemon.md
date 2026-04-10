import os
import sys
import logging
import subprocess
from pathlib import Path
from google import genai
from google.genai import errors
from dotenv import load_dotenv
import graph_builder
import metrics

# Configure explicit paths
SCRIPT_DIR = Path(__file__).parent.resolve()

# Load environment variables explicitly from the script directory
load_dotenv(SCRIPT_DIR / ".env")

VAULT_PATH_RAW = os.getenv("VAULT_PATH")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not VAULT_PATH_RAW or not GEMINI_API_KEY:
    print("Error: VAULT_PATH and GEMINI_API_KEY must be set in .env")
    sys.exit(1)

# Clean terminal escape characters
CLEANED_VAULT_PATH = VAULT_PATH_RAW.replace("\\ ", " ").replace("\\~", "~").replace('\\"', '"').replace("\\'", "'")

VAULT_DIR = Path(CLEANED_VAULT_PATH).expanduser().resolve()
WIKI_DIR = VAULT_DIR / "wiki"
REPORT_PATH = VAULT_DIR / "Maintenance_Report.md"

# Configure Gemini
client = genai.Client(api_key=GEMINI_API_KEY)

# Configurable models (default to 3.1 pro if not provided)
MODEL_NAME = os.getenv("GEMINI_MODEL_LINTER", "gemini-3.1-pro-preview")

# Configure Robust Rotating Logging
LOG_DIR = SCRIPT_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

import sys
class APIRedactingFormatter(logging.Formatter):
    """Custom formatter to ensure API keys are never leaked in logs."""
    def __init__(self, fmt, datefmt, api_key):
        super().__init__(fmt, datefmt)
        self.api_key = api_key

    def format(self, record):
        original_msg = super().format(record)
        if self.api_key and self.api_key in original_msg:
            return original_msg.replace(self.api_key, "***REDACTED_API_KEY***")
        return original_msg

from logging.handlers import RotatingFileHandler

log_formatter = APIRedactingFormatter(
    '%(asctime)s - %(message)s',
    '%Y-%m-%d %H:%M:%S',
    GEMINI_API_KEY
)

log_handler = RotatingFileHandler(
    LOG_DIR / "linter.log", maxBytes=5*1024*1024, backupCount=2
)
log_handler.setFormatter(log_formatter)

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(log_formatter)

logging.basicConfig(
    level=logging.INFO,
    handlers=[log_handler, stream_handler]
)

def send_notification(title, message):
    """Sends a native macOS push notification safely."""
    # Prevent AppleScript injection by fully escaping both backslashes and double quotes
    escaped_title = title.replace('\\', '\\\\').replace('"', '\\"')
    escaped_message = message.replace('\\', '\\\\').replace('"', '\\"')
    apple_script = f'display notification "{escaped_message}" with title "{escaped_title}"'
    subprocess.run(["osascript", "-e", apple_script])

def collect_wiki_contents():
    """Recursively reads all markdown files in the wiki directory."""
    wiki_contents = []

    if not WIKI_DIR.exists():
        logging.warning(f"Wiki directory {WIKI_DIR} does not exist.")
        return ""

    for file_path in WIKI_DIR.rglob("*.md"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                # Store with the relative filepath for context
                rel_path = file_path.relative_to(VAULT_DIR)
                wiki_contents.append(f"### File: {rel_path}\n{content}\n")
        except Exception as e:
            logging.error(f"Failed to read {file_path}: {e}")

    return "\n".join(wiki_contents)

def lint_wiki():
    logging.info("Starting weekly synthesis linter...")

    wiki_payload = collect_wiki_contents()

    if not wiki_payload.strip():
        logging.info("No wiki contents found to lint.")
        return

    prompt = f"""
You are the master Synthesis Linter for an autonomous Obsidian knowledge graph.
Your singular directive is to audit the entire wiki graph, looking for the hidden architecture of thought.

Review the vault contents provided within the <vault_content> tags below.
You must produce a highly structured, beautiful Markdown report with the following exact sections:

# 🔮 Weekly Synthesis Report

## 🚨 Logical Contradictions
Identify areas where two notes seem to disagree or present conflicting information. Provide the file paths and explain the conflict. If none, say "No contradictions detected."

## 👻 Orphaned Nodes
Identify concepts or entities that are isolated. Suggest specific existing notes they should be linked to using `[[Wikilinks]]`.

## ✨ Synthesis Opportunities
Where can two separate notes be merged to form a stronger, unified thesis? Suggest new connections that are not explicitly stated but logically follow.

## 🛠️ Actionable Recommendations
Provide a checklist (`- [ ]`) of 3 to 5 specific things the user should do this week to improve the graph's structure or depth.

<vault_content>
{wiki_payload}
</vault_content>
"""

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )

        # Track API Token Costs
        if hasattr(response, 'usage_metadata'):
            metrics.track_usage("lint_wiki.py", MODEL_NAME, response.usage_metadata)

        with open(REPORT_PATH, "w", encoding="utf-8") as f:
            f.write(response.text)

        logging.info(f"Successfully generated Maintenance Report at {REPORT_PATH}")

        # Update graph JSON
        try:
            graph_builder.build_graph()
        except Exception as ge:
            logging.error(f"Failed to rebuild graph after linting: {ge}")

        send_notification("Daemon.md Linter", "Weekly Maintenance Report generated.")

    except errors.APIError as api_err:
        logging.error(f"Gemini API Error during synthesis (Check token limits or quota): {api_err}")
        send_notification("Daemon.md Linter Error", "Gemini API failed. See linter logs.")
    except Exception as e:
        logging.error(f"Failed to run synthesis linter: {e}")
        send_notification("Daemon.md Linter Error", "Failed to generate Maintenance Report.")

if __name__ == "__main__":
    lint_wiki()
