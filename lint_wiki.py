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
    subprocess.run([
        "osascript",
        "-e", "on run argv",
        "-e", "display notification (item 2 of argv) with title (item 1 of argv)",
        "-e", "end run",
        title, message
    ])

def collect_wiki_content_chunks(max_chars=50000):
    """Recursively reads markdown files and yields chunks to avoid token limits."""
    if not WIKI_DIR.exists():
        logging.warning(f"Wiki directory {WIKI_DIR} does not exist.")
        return []

    chunks = []
    current_chunk = []
    current_length = 0

    for file_path in WIKI_DIR.rglob("*.md"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                rel_path = file_path.relative_to(VAULT_DIR)
                file_text = f"### File: {rel_path}\n{content}\n"

                if current_length + len(file_text) > max_chars and current_chunk:
                    chunks.append("\n".join(current_chunk))
                    current_chunk = [file_text]
                    current_length = len(file_text)
                else:
                    current_chunk.append(file_text)
                    current_length += len(file_text)
        except Exception as e:
            logging.error(f"Failed to read {file_path}: {e}")

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return chunks

def lint_wiki():
    logging.info("Starting weekly synthesis linter...")

    wiki_chunks = collect_wiki_content_chunks()

    if not wiki_chunks:
        logging.info("No wiki contents found to lint.")
        return

    # If there is only one chunk, do a single prompt. If multiple, aggregate.
    final_report = ""
    chunk_reports = []

    for idx, chunk in enumerate(wiki_chunks):
        logging.info(f"Processing chunk {idx + 1} of {len(wiki_chunks)}...")
        prompt = f"""
You are the master Synthesis Linter for an autonomous Obsidian knowledge graph.
Your singular directive is to audit the provided portion of the wiki graph, looking for the hidden architecture of thought.

Review the vault contents provided within the <vault_content> tags below.
You must produce a highly structured, beautiful Markdown report focusing on the following sections:

## 🚨 Logical Contradictions
Identify areas where two notes seem to disagree or present conflicting information. Provide the file paths and explain the conflict. If none, say "No contradictions detected."

## 👻 Orphaned Nodes
Identify concepts or entities that are isolated. Suggest specific existing notes they should be linked to using `[[Wikilinks]]`.

## ✨ Synthesis Opportunities
Where can two separate notes be merged to form a stronger, unified thesis? Suggest new connections that are not explicitly stated but logically follow.

## 🛠️ Actionable Recommendations
Provide a checklist (`- [ ]`) of specific things the user should do to improve the graph's structure or depth based on these files.

<vault_content>
{chunk}
</vault_content>
"""
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
            )

            if hasattr(response, 'usage_metadata'):
                metrics.track_usage("lint_wiki.py", MODEL_NAME, response.usage_metadata)

            chunk_reports.append(response.text)

        except errors.APIError as api_err:
            logging.error(f"Gemini API Error during synthesis chunk {idx+1}: {api_err}")
            send_notification("Daemon.md Linter Error", f"Gemini API failed on chunk {idx+1}.")
            return
        except Exception as e:
            logging.error(f"Failed to run synthesis linter on chunk {idx+1}: {e}")
            send_notification("Daemon.md Linter Error", f"Failed to generate chunk {idx+1}.")
            return

    # Compile the final report
    if len(chunk_reports) == 1:
        final_report = f"# 🔮 Weekly Synthesis Report\n\n{chunk_reports[0]}"
    else:
        final_report = "# 🔮 Weekly Synthesis Report\n\n"
        for i, report in enumerate(chunk_reports):
            final_report += f"### Part {i+1}\n\n{report}\n\n---\n\n"

    try:
        with open(REPORT_PATH, "w", encoding="utf-8") as f:
            f.write(final_report)

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
