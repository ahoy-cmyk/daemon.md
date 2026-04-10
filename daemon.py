import os
import sys
import time
import json
import logging
import subprocess
import shutil
import threading
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from google import genai
from google.genai import types
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

# Clean terminal escape characters (e.g. "Mobile\ Documents" -> "Mobile Documents")
CLEANED_VAULT_PATH = VAULT_PATH_RAW.replace("\\ ", " ").replace("\\~", "~").replace('\\"', '"').replace("\\'", "'")

VAULT_DIR = Path(CLEANED_VAULT_PATH).expanduser().resolve()
RAW_DIR = VAULT_DIR / "raw"
FAILED_DIR = VAULT_DIR / "failed"
GEMINI_MD_PATH = VAULT_DIR / "GEMINI.md"

# Ensure directories exist
RAW_DIR.mkdir(parents=True, exist_ok=True)
FAILED_DIR.mkdir(parents=True, exist_ok=True)

# Configure Gemini
client = genai.Client(api_key=GEMINI_API_KEY)

# Use 3.0 flash as requested
# Depending on SDK version, we can configure json response.
MODEL_NAME = "gemini-3.0-flash"

# Configure Robust Rotating Logging
LOG_DIR = SCRIPT_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

from logging.handlers import RotatingFileHandler
log_handler = RotatingFileHandler(
    LOG_DIR / "daemon.log", maxBytes=5*1024*1024, backupCount=2
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

def read_existing_wiki_contents():
    """Reads all existing files in the vault to provide context for rewriting."""
    # To properly rewrite files, the LLM needs to know what currently exists.
    # We will build a map of filepaths and their current content.
    wiki_context = ""
    for root, dirs, files in os.walk(VAULT_DIR):
        for file in files:
            if file.endswith(".md") and "raw" not in root and file != "GEMINI.md":
                file_path = Path(root) / file
                rel_path = file_path.relative_to(VAULT_DIR)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    wiki_context += f"### Existing File: {rel_path}\n{content}\n\n"
                except Exception as e:
                    logging.error(f"Failed to read existing file for context {file_path}: {e}")
    return wiki_context

def process_raw_file(file_path):
    """Processes a new raw markdown file with Gemini."""
    file_path = Path(file_path)
    if not file_path.exists():
        return

    logging.info(f"Processing new raw file: {file_path.name}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_content = f.read()

        master_prompt = ""
        if GEMINI_MD_PATH.exists():
            with open(GEMINI_MD_PATH, "r", encoding="utf-8") as f:
                master_prompt = f.read()

        existing_wiki_context = read_existing_wiki_contents()

        prompt = f"""
{master_prompt}

You are an automated knowledge extraction system.
Analyze the following newly added markdown content.

If the information updates existing knowledge, output a 'wiki_update'. For wiki_updates, you MUST rewrite the ENTIRE existing target file (if any) with the new context seamlessly integrated. Do not just append. We have provided the existing contents of the vault below.
If the information is an actionable task or an action item executed, output a 'task_completion'.

Output your response strictly as a JSON array of objects, where each object has:
- `type`: Either "wiki_update" or "task_completion"
- `filepath`: The relative path within the vault where this should be written (e.g., "wiki/concepts/AI.md" or "Action_Items/Task1.md")
- `content`: The complete, fully written markdown content to be saved to the file.

EXISTING VAULT CONTENTS (Use this to rewrite files accurately without losing existing info):
---
{existing_wiki_context}
---

NEW RAW CONTENT TO INGEST:
---
{raw_content}
---
"""

        # Using generation_config for JSON mode
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            )
        )

        try:
            # We expect a JSON array
            updates = json.loads(response.text)
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse Gemini output as JSON: {e}")
            logging.error(f"Raw output: {response.text}")
            # Move to failed directory to prevent infinite retry loops
            failed_path = FAILED_DIR / file_path.name
            shutil.move(str(file_path), str(failed_path))
            logging.info(f"Moved unparseable raw file to {failed_path}")
            send_notification("Daemon.md Error", "Failed to parse Gemini output as JSON. File moved to failed/")
            return

        actions_taken = []

        for update in updates:
            update_type = update.get("type")
            rel_path = update.get("filepath")
            content = update.get("content")

            if not all([update_type, rel_path, content]):
                logging.warning(f"Incomplete update object: {update}")
                continue

            target_path = VAULT_DIR / rel_path

            # Ensure the directory exists
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # Always overwrite (as requested for both tasks and wiki_updates to maintain formatting)
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(content)

            actions_taken.append(f"Updated {target_path.name}")
            logging.info(f"Wrote to {target_path}")

        # Delete the raw file
        file_path.unlink()
        logging.info(f"Deleted raw file: {file_path.name}")

        # Update graph JSON
        try:
            graph_builder.build_graph()
        except Exception as ge:
            logging.error(f"Failed to rebuild graph after ingestion: {ge}")

        if actions_taken:
            send_notification("Daemon.md Updated", ", ".join(actions_taken))
        else:
            send_notification("Daemon.md", "Processed file but no actions taken.")

    except Exception as e:
        logging.error(f"Error processing {file_path.name}: {e}")
        # Move to failed directory to prevent infinite retry loops
        try:
            failed_path = FAILED_DIR / file_path.name
            shutil.move(str(file_path), str(failed_path))
            logging.info(f"Moved errored raw file to {failed_path}")
            send_notification("Daemon.md Error", f"Failed to process {file_path.name}. File moved to failed/")
        except Exception as move_e:
            logging.error(f"Failed to move {file_path.name} to failed directory: {move_e}")
            send_notification("Daemon.md Error", f"Critical Error processing {file_path.name}")
processing_files = set()
processing_lock = threading.Lock()

def safe_process_raw_file(file_path):
    """Wrapper to prevent duplicate processing of the same file."""
    path_str = str(file_path)

    with processing_lock:
        if path_str in processing_files:
            return
        processing_files.add(path_str)

    try:
        process_raw_file(file_path)
    finally:
        with processing_lock:
            if path_str in processing_files:
                processing_files.remove(path_str)

class RawFolderHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith('.md'):
            # Small delay to ensure file is completely written before reading
            time.sleep(1)
            safe_process_raw_file(event.src_path)

    def on_moved(self, event):
        # Catch files moved/renamed into the directory
        if not event.is_directory and event.dest_path.endswith('.md'):
            if Path(event.dest_path).parent == RAW_DIR:
                time.sleep(1)
                safe_process_raw_file(event.dest_path)

def periodic_scan():
    """Fallback scanner to catch files if filesystem events fail (common on iCloud)."""
    for file in RAW_DIR.glob("*.md"):
        if file.exists():
            safe_process_raw_file(file)

def main():
    logging.info(f"Starting Daemon.md watching {RAW_DIR}")

    event_handler = RawFolderHandler()
    observer = Observer()
    observer.schedule(event_handler, str(RAW_DIR), recursive=False)
    observer.start()

    # Process any files that are already in the raw directory on startup
    periodic_scan()

    try:
        while True:
            # Poll every 5 seconds as a fallback to watchdog
            time.sleep(5)
            periodic_scan()
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    main()
