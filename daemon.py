import os
import sys
import time
import json
import logging
import subprocess
import shutil
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from google import genai
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

# Configurable models (default to 3.1 flash-lite if not provided)
MODEL_NAME = os.getenv("GEMINI_MODEL_DAEMON", "gemini-3.1-flash-lite-preview")

# Configure Robust Rotating Logging
LOG_DIR = SCRIPT_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

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
    LOG_DIR / "daemon.log", maxBytes=5*1024*1024, backupCount=2
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

def get_graph_context():
    """Reads latent_space.json to provide structural context instead of raw file reads."""
    # Performance Optimization: Sending the entire vault content for every note ingestion
    # burns massive API tokens and causes extreme latency as the vault grows.
    # Instead, we pass the latent_space.json map. The LLM can use this to know
    # what concepts exist and how they are structured without reading every word.
    context_file = SCRIPT_DIR / "visualizer" / "public" / "latent_space.json"
    if context_file.exists():
        try:
            with open(context_file, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logging.error(f"Failed to read graph context: {e}")
    return '{"nodes":[],"links":[]}'

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

        graph_context = get_graph_context()

        prompt = f"""
{master_prompt}

You are an automated knowledge extraction system.
Analyze the following newly added markdown content.

If the information updates existing knowledge, output a 'wiki_update'. For wiki_updates, you MUST rewrite the ENTIRE existing target file (if any) with the new context seamlessly integrated. Do not just append. We have provided the existing semantic map of the vault below so you know what files already exist to update.
If the information is an actionable task or an action item executed, output a 'task_completion'.

Output your response strictly as a JSON array of objects, where each object has:
- `type`: Either "wiki_update" or "task_completion"
- `filepath`: The relative path within the vault where this should be written (e.g., "wiki/concepts/AI.md" or "Action_Items/Task1.md")
- `content`: The complete, fully written markdown content to be saved to the file.

EXISTING VAULT MAP (JSON nodes/links indicating the current layout of the knowledge base):
---
{graph_context}
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

        # Track API Token Costs
        if hasattr(response, 'usage_metadata'):
            metrics.track_usage("daemon.py", MODEL_NAME, response.usage_metadata)

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

            target_path = (VAULT_DIR / rel_path).resolve()

            # Prevent Directory Traversal
            if not target_path.is_relative_to(VAULT_DIR):
                logging.error(f"Path traversal blocked: Attempted to write to {target_path}")
                continue

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

# Global ThreadPoolExecutor for background processing
executor = ThreadPoolExecutor(max_workers=4)

def handle_file_async(file_path):
    """Wait briefly, then process the file. This runs in a worker thread."""
    time.sleep(1)
    safe_process_raw_file(file_path)

class RawFolderHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith('.md'):
            executor.submit(handle_file_async, event.src_path)

    def on_moved(self, event):
        # Catch files moved/renamed into the directory
        if not event.is_directory and event.dest_path.endswith('.md'):
            if Path(event.dest_path).parent == RAW_DIR:
                executor.submit(handle_file_async, event.dest_path)

    def on_modified(self, event):
        # Catch files synced via iCloud that may bypass creation events
        if not event.is_directory and event.src_path.endswith('.md'):
            executor.submit(handle_file_async, event.src_path)

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
            # Lazy sweep every 60 seconds as a highly efficient fallback to watchdog
            time.sleep(60)
            periodic_scan()
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    main()
