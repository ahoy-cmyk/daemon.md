import os
import sys
import logging
import subprocess
from pathlib import Path
from google import genai
from dotenv import load_dotenv
import graph_builder

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

# Use 3.1 pro for deep synthesis as requested
MODEL_NAME = "gemini-3.1-pro"

# Configure Robust Rotating Logging
LOG_DIR = SCRIPT_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

from logging.handlers import RotatingFileHandler
log_handler = RotatingFileHandler(
    LOG_DIR / "linter.log", maxBytes=5*1024*1024, backupCount=2
)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[log_handler, logging.StreamHandler(sys.stdout)]
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
You are the Synthesis Linter for an autonomous knowledge graph.
Your job is to audit the entire wiki graph for:
1. Logical contradictions
2. Orphaned nodes (concepts/entities that are disconnected)
3. Synthesis opportunities (where two separate notes could be combined or linked to form a stronger idea)

Review the following wiki contents (each section labeled with its filepath).
Provide a structured markdown report detailing your findings and suggesting specific improvements.

WIKI CONTENTS:
---
{wiki_payload}
---
"""

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )

        with open(REPORT_PATH, "w", encoding="utf-8") as f:
            f.write(response.text)

        logging.info(f"Successfully generated Maintenance Report at {REPORT_PATH}")

        # Update graph JSON
        try:
            graph_builder.build_graph()
        except Exception as ge:
            logging.error(f"Failed to rebuild graph after linting: {ge}")

        send_notification("Daemon.md Linter", "Weekly Maintenance Report generated.")

    except Exception as e:
        logging.error(f"Failed to run synthesis linter: {e}")
        send_notification("Daemon.md Linter Error", "Failed to generate Maintenance Report.")

if __name__ == "__main__":
    lint_wiki()
