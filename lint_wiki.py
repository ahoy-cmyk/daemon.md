import os
import sys
import logging
import subprocess
import json
from pathlib import Path
from google import genai
from google.genai import errors
from google.genai import types
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
    subprocess.run([
        "osascript",
        "-e", "on run argv",
        "-e", "display notification (item 2 of argv) with title (item 1 of argv)",
        "-e", "end run",
        title, message
    ])

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

    # Read the continuous ledger (log.md) at the vault root
    log_path = VAULT_DIR / "log.md"
    if log_path.exists():
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                content = f.read()
                wiki_contents.append(f"### File: log.md\n{content}\n")
        except Exception as e:
            logging.error(f"Failed to read {log_path}: {e}")

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

First, you must produce a highly structured, beautiful Markdown report with the following exact sections:

# 🔮 Weekly Synthesis Report

## 🚨 Logical Contradictions
Identify areas where two notes seem to disagree or present conflicting information. Provide the file paths and explain the conflict. If none, say "No contradictions detected."

## 👻 Orphaned Nodes
Identify concepts or entities that are isolated. Suggest specific existing notes they should be linked to using `[[Wikilinks]]`.

## ✨ Synthesis Opportunities
Where can two separate notes be merged to form a stronger, unified thesis? Suggest new connections that are not explicitly stated but logically follow.

## 🛠️ Actionable Recommendations
Provide a checklist (`- [ ]`) of 3 to 5 specific things the user should do this week to improve the graph's structure or depth.

## 📅 The Weekly Timeline
A chronological narrative summarizing the evolution of my thoughts, the data I ingested, and the projects I focused on over the past 7 days. Group this by themes or days to show the momentum of the vault.

You MUST output your response strictly as a single JSON object. The JSON object must contain exactly two fields:
1. `report`: A string containing the entire formatting Markdown report (with the exact sections listed above).
2. `fixes`: An array of objects representing the automated file changes needed to apply your recommendations.

For each object in the `fixes` array, include:
- `filepath`: The relative path within the vault where this should be written (e.g., "wiki/concepts/AI.md").
- `content`: The complete, fully written markdown content to be saved to the file, incorporating the fixes.
- `reason`: A short explanation of what was fixed (e.g., "Added wikilink to orphaned node").

If no automated fixes are needed, `fixes` should be an empty array.

<vault_content>
{wiki_payload}
</vault_content>
"""

    try:
        # Define strict JSON schema
        linter_schema = types.Schema(
            type=types.Type.OBJECT,
            properties={
                "report": types.Schema(type=types.Type.STRING),
                "fixes": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "filepath": types.Schema(type=types.Type.STRING),
                            "content": types.Schema(type=types.Type.STRING),
                            "reason": types.Schema(type=types.Type.STRING)
                        },
                        required=["filepath", "content", "reason"]
                    )
                )
            },
            required=["report", "fixes"]
        )

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=linter_schema
            )
        )

        # Track API Token Costs
        if hasattr(response, 'usage_metadata'):
            metrics.track_usage("lint_wiki.py", MODEL_NAME, response.usage_metadata)

        response_text = response.text

        try:
            parsed_response = json.loads(response_text)
            markdown_report = parsed_response.get("report", "")
            automated_fixes = parsed_response.get("fixes", [])
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse JSON response: {e}")
            markdown_report = "Failed to parse API response as JSON."
            automated_fixes = []

        applied_fixes_log = []

        # Apply the automated fixes
        if automated_fixes:
            logging.info(f"Applying {len(automated_fixes)} automated fixes...")
            for fix in automated_fixes:
                rel_path = fix.get("filepath")
                content = fix.get("content")
                reason = fix.get("reason", "Automated fix applied.")

                if not rel_path or not content:
                    logging.warning(f"Incomplete fix object skipped: {fix}")
                    continue

                target_path = (VAULT_DIR / rel_path).resolve()

                # Prevent Directory Traversal
                if not target_path.is_relative_to(VAULT_DIR):
                    logging.error(f"Path traversal blocked in automated fix: Attempted to write to {target_path}")
                    continue

                # Safety Net: Prevent massive truncations due to hallucinations
                if target_path.exists():
                    try:
                        with open(target_path, "r", encoding="utf-8") as f:
                            old_content = f.read()

                        if len(old_content) > 500 and len(content) < len(old_content) * 0.5:
                            logging.warning(f"Safety trigger: AI tried to reduce file size by > 50%. Skipping {rel_path}.")
                            applied_fixes_log.append(f"- ⚠️ **Skipped {rel_path}**: AI attempted to truncate > 50% of the file.")
                            continue
                    except Exception as e:
                        logging.error(f"Failed to read existing content for safety check on {target_path}: {e}")

                try:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(target_path, "w", encoding="utf-8") as f:
                        f.write(content)

                    logging.info(f"Automated fix applied to {target_path.name}: {reason}")
                    applied_fixes_log.append(f"- **{rel_path}**: {reason}")
                except Exception as e:
                    logging.error(f"Failed to apply fix to {target_path}: {e}")

        # Append applied fixes to the Markdown report
        if applied_fixes_log:
            markdown_report += "\n\n## 🤖 Automatically Applied Fixes\n"
            markdown_report += "\n".join(applied_fixes_log)
        else:
            markdown_report += "\n\n## 🤖 Automatically Applied Fixes\nNo automated fixes were applied during this run.\n"

        with open(REPORT_PATH, "w", encoding="utf-8") as f:
            f.write(markdown_report)

        logging.info(f"Successfully generated Maintenance Report at {REPORT_PATH}")

        # Update graph JSON
        try:
            graph_builder.build_graph()
        except Exception as ge:
            logging.error(f"Failed to rebuild graph after linting: {ge}")

        notification_msg = "Weekly Maintenance Report generated."
        if applied_fixes_log:
            notification_msg += f" {len(applied_fixes_log)} automatic fixes applied."

        send_notification("Daemon.md Linter", notification_msg)

    except errors.APIError as api_err:
        logging.error(f"Gemini API Error during synthesis (Check token limits or quota): {api_err}")
        send_notification("Daemon.md Linter Error", "Gemini API failed. See linter logs.")
    except Exception as e:
        logging.error(f"Failed to run synthesis linter: {e}")
        send_notification("Daemon.md Linter Error", "Failed to generate Maintenance Report.")

if __name__ == "__main__":
    lint_wiki()
