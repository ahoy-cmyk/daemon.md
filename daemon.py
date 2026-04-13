import os
import sys
import time
import json
import logging
import subprocess
import datetime
import shutil
import threading
import collections
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from google import genai
from google.genai import types
import graph_builder
import metrics
import config
from config import SUPPORTED_EXTENSIONS
from typing import Dict, Deque
from config import (
    VAULT_DIR,
    RAW_DIR,
    ARCHIVE_DIR,
    WIKI_DIR,
    FAILED_DIR,
    GEMINI_MD_PATH,
    SCRIPT_DIR,
)

# Track when the daemon writes a file so we don't treat it as a manual user edit
daemon_written_files = {}
daemon_write_lock = threading.Lock()

# Configure Gemini
client = genai.Client(api_key=config.GEMINI_API_KEY)

# Configurable models (default to 3.1 flash-lite if not provided)
MODEL_NAME = os.getenv("GEMINI_MODEL_DAEMON", "gemini-3.1-flash-lite-preview")

# Configurable polling interval (default to 15 seconds)
POLL_INTERVAL = int(os.getenv("DAEMON_POLL_INTERVAL", "15"))


# Configure Robust Rotating Logging
LOG_DIR = SCRIPT_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


class APIRedactingFormatter(logging.Formatter):
    """Custom formatter to ensure API keys are never leaked in logs."""

    def __init__(self, fmt, datefmt, api_key=None):
        super().__init__(fmt, datefmt)
        self.api_key = api_key

    def format(self, record):
        original_msg = super().format(record)
        if self.api_key and self.api_key in original_msg:
            return original_msg.replace(self.api_key, "***REDACTED_API_KEY***")
        return original_msg


from logging.handlers import RotatingFileHandler

log_formatter = APIRedactingFormatter(
    "%(asctime)s - %(message)s", "%Y-%m-%d %H:%M:%S", config.GEMINI_API_KEY
)

log_handler = RotatingFileHandler(
    LOG_DIR / "daemon.log", maxBytes=5 * 1024 * 1024, backupCount=2
)
log_handler.setFormatter(log_formatter)

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(log_formatter)

logging.basicConfig(level=logging.INFO, handlers=[log_handler, stream_handler])


def send_notification(title, message):
    """Sends a native macOS push notification safely."""
    subprocess.run(
        [
            "osascript",
            "-e",
            "on run argv",
            "-e",
            "display notification (item 2 of argv) with title (item 1 of argv)",
            "-e",
            "end run",
            title,
            message,
        ]
    )


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
            logging.error(f"Failed to read graph context: {e}", exc_info=True)
    return '{"nodes":[],"links":[]}'


def process_file_core(file_path, is_rebuild=False, original_timestamp=None):
    """Core logic to process a file with Gemini. Returns (success_bool, actions_taken_list)."""
    file_path = Path(file_path)
    if not file_path.exists():
        return False, []

    if not is_rebuild:
        # Wait for the file to finish writing (e.g., from iCloud or Voice Memos)
        # Give up after 10 attempts (10 seconds)
        for _ in range(10):
            try:
                if file_path.stat().st_size > 0:
                    break
            except FileNotFoundError:
                return False, []
            except OSError:
                pass
            time.sleep(1)

    logging.info(f"Processing file: {file_path.name}")

    uploaded_file = None
    try:
        master_prompt = ""
        if GEMINI_MD_PATH.exists():
            with open(GEMINI_MD_PATH, "r", encoding="utf-8") as f:
                master_prompt = f.read()

        graph_context = get_graph_context()

        system_instruction = f"""
{master_prompt}

You are an automated knowledge extraction system.

If the information updates existing knowledge, output a 'wiki_update'. For wiki_updates, you MUST rewrite the ENTIRE existing target file (if any) with the new context seamlessly integrated. Do not just append. We have provided the existing semantic map of the vault below so you know what files already exist to update.
If the information is an actionable task or an action item executed, output a 'task_completion'.

Output your response strictly as a JSON array of objects, where each object has:
- `type`: Either "wiki_update" or "task_completion"
- `filepath`: The relative path within the vault where this should be written (e.g., "wiki/concepts/AI.md" or "Action_Items/Task1.md")
- `content`: The complete, fully written markdown content to be saved to the file.

CRITICAL INSTRUCTION FOR MARKDOWN CONTENT:
You MUST prepend standard YAML frontmatter to the very top of EVERY markdown file you generate.
The frontmatter MUST contain `created_at` and `updated_at` fields in ISO 8601 format.
Example:
---
created_at: "2024-05-12T10:30:00Z"
updated_at: "2024-05-12T10:30:00Z"
---
# The Rest Of Your Content

EXISTING VAULT MAP (JSON nodes/links indicating the current layout of the knowledge base):
---
{graph_context}
---
"""

        # Handle text vs audio files
        is_audio = file_path.suffix.lower() in {
            ".m4a",
            ".mp3",
            ".wav",
            ".ogg",
            ".flac",
            ".aac",
        }

        if is_audio:
            logging.info(f"Uploading audio file to Gemini API: {file_path.name}")
            # Wait for file to be fully downloaded from iCloud before copying
            retries = 0
            while retries < 15:
                try:
                    stat = file_path.stat()
                    if stat.st_size > 0:
                        # Wait a little to see if the size is still changing
                        time.sleep(0.5)
                        new_stat = file_path.stat()
                        if stat.st_size == new_stat.st_size:
                            break  # File seems stable
                except Exception:
                    pass
                time.sleep(1)
                retries += 1

            # Create a temporary copy of the file to avoid iCloud Resource Deadlock
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=file_path.suffix
            ) as tmp:
                temp_path = tmp.name

            try:
                # Do not use shutil.copy2 or shutil.copyfile, as they use fcopyfile which causes
                # [Errno 11] Resource deadlock avoided on iCloud paths in macOS.
                # Use raw os reads if possible, or standard chunks.
                # Retry loop to handle transient Errno 11 from iCloud syncing locks.
                chunk_size = 64 * 1024
                copy_success = False
                copy_attempts = 0
                while not copy_success and copy_attempts < 5:
                    try:
                        with open(file_path, "rb") as fsrc:
                            with open(temp_path, "wb") as fdst:
                                while True:
                                    chunk = fsrc.read(chunk_size)
                                    if not chunk:
                                        break
                                    fdst.write(chunk)
                        copy_success = True
                    except OSError as e:
                        if e.errno == 11:  # Resource deadlock avoided
                            copy_attempts += 1
                            logging.warning(
                                f"Resource deadlock on {file_path.name}, retrying {copy_attempts}/5..."
                            )
                            time.sleep(1)
                        else:
                            raise e

                if not copy_success:
                    raise OSError(
                        f"Failed to copy {file_path.name} after 5 attempts due to resource deadlock."
                    )

                uploaded_file = client.files.upload(file=temp_path)
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

            prompt = """
Listen to the attached audio file. Carefully transcribe and analyze the spoken content.
Extract the core concepts, tasks, and entities exactly as you would for a text note.
"""
            api_contents = [uploaded_file, prompt]
        else:
            with open(file_path, "r", encoding="utf-8") as f:
                raw_content = f.read()
            prompt = f"""
Analyze the following newly added text content.

NEW RAW CONTENT TO INGEST:
---
{raw_content}
---
"""
            api_contents = prompt

        # Define strict JSON schema
        update_schema = types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "type": types.Schema(
                        type=types.Type.STRING, enum=["wiki_update", "task_completion"]
                    ),
                    "filepath": types.Schema(type=types.Type.STRING),
                    "content": types.Schema(type=types.Type.STRING),
                },
                required=["type", "filepath", "content"],
            ),
        )

        # Using generation_config for JSON mode, strict schema, and system instructions
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=api_contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=update_schema,
                system_instruction=system_instruction,
            ),
        )

        # Track API Token Costs
        if hasattr(response, "usage_metadata"):
            metrics.track_usage("daemon.py", MODEL_NAME, response.usage_metadata)

        try:
            # We expect a JSON array
            updates = json.loads(response.text)
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse Gemini output as JSON: {e}", exc_info=True)
            logging.error(f"Raw output: {response.text}")
            return False, []

        actions_taken = []

        for update in updates:
            update_type = update.get("type")
            rel_path = update.get("filepath")
            content = update.get("content")

            if not all([update_type, rel_path, content]):
                logging.warning(f"Incomplete update object: {update}")
                continue

            # Prevent empty file overwrites
            if not str(content).strip():
                logging.warning(f"Skipping empty content update for {rel_path}")
                continue

            target_path = (VAULT_DIR / rel_path).resolve()

            # Prevent Directory Traversal
            if not target_path.is_relative_to(VAULT_DIR):
                logging.error(
                    f"Path traversal blocked: Attempted to write to {target_path}"
                )
                continue

            # Ensure the directory exists
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # Enforce strict metadata preservation via Python
            now_iso = datetime.datetime.utcnow().isoformat() + "Z"

            if original_timestamp:
                try:
                    # original_timestamp is formatted as "YYYYMMDD_HHMMSS"
                    dt = datetime.datetime.strptime(original_timestamp, "%Y%m%d_%H%M%S")
                    created_iso = dt.isoformat() + "Z"
                except ValueError:
                    created_iso = now_iso
            else:
                # If target exists, try to preserve its original created_at from YAML frontmatter
                created_iso = now_iso
                if target_path.exists():
                    try:
                        import re

                        with open(target_path, "r", encoding="utf-8") as f:
                            existing_content = f.read()
                        match = re.search(
                            r"^---\n.*?created_at:\s*[\"']?(.*?)[\"']?\n.*?---",
                            existing_content,
                            re.DOTALL,
                        )
                        if match:
                            created_iso = match.group(1).strip()
                    except Exception:
                        pass

            # Strip LLM's hallucinated frontmatter if present to ensure we enforce the real one
            import re

            content = re.sub(r"^---\n.*?\n---\n+", "", content, flags=re.DOTALL).strip()

            final_content = f'---\ncreated_at: "{created_iso}"\nupdated_at: "{now_iso}"\n---\n\n{content}'

            # Always overwrite (as requested for both tasks and wiki_updates to maintain formatting)
            with daemon_write_lock:
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write(final_content)
                # Record the exact time we wrote this to ignore the subsequent filesystem event
                daemon_written_files[str(target_path)] = time.time()

            actions_taken.append(f"Updated {target_path.name}")
            logging.info(f"Wrote to {target_path}")

        # Update graph JSON
        try:
            graph_builder.build_graph()
        except Exception as ge:
            logging.error(
                f"Failed to rebuild graph after ingestion: {ge}", exc_info=True
            )

        if actions_taken:
            send_notification("Daemon.md Updated", ", ".join(actions_taken))
        else:
            send_notification("Daemon.md", "Processed file but no actions taken.")

        return True, actions_taken

    except Exception as e:
        logging.error(f"Error processing {file_path.name}: {e}", exc_info=True)
        return False, []
    finally:
        if uploaded_file:
            try:
                logging.info(
                    f"Deleting uploaded media from Gemini API: {uploaded_file.name}"
                )
                client.files.delete(name=uploaded_file.name)
            except Exception as e:
                logging.error(
                    f"Failed to delete uploaded media {uploaded_file.name}: {e}"
                )


def move_to_failed(file_path: Path):
    """Safely moves a failed file, with a fallback to unlink to prevent infinite loops."""
    if not file_path.exists():
        return
    try:
        failed_path = FAILED_DIR / file_path.name
        if failed_path.exists():
            failed_path = (
                FAILED_DIR / f"{file_path.stem}_{int(time.time())}{file_path.suffix}"
            )
        shutil.move(str(file_path), str(failed_path))
        logging.info(f"Moved errored raw file to {failed_path}")
        send_notification(
            "Daemon.md Error",
            f"Failed to process {file_path.name}. File moved to failed/",
        )
    except Exception as move_e:
        logging.error(
            f"Failed to move {file_path.name} to failed directory: {move_e}",
            exc_info=True,
        )
        try:
            file_path.unlink(missing_ok=True)
            logging.info(
                f"Deleted {file_path.name} as a fallback to prevent infinite loop."
            )
        except Exception as unlink_e:
            logging.error(
                f"Fallback deletion failed for {file_path.name}: {unlink_e}",
                exc_info=True,
            )


# Global tracker for API calls to prevent runaway loops
api_calls_tracker: Deque[float] = collections.deque()
API_CALL_LIMIT = int(os.getenv("DAEMON_API_CALL_LIMIT", "50"))
API_CALL_WINDOW = int(os.getenv("DAEMON_API_CALL_WINDOW", "60"))  # seconds


def check_circuit_breaker():
    """Checks if we are in a runaway state. Halts if true."""
    now = time.time()

    # Remove old timestamps
    while api_calls_tracker and now - api_calls_tracker[0] > API_CALL_WINDOW:
        api_calls_tracker.popleft()

    api_calls_tracker.append(now)

    if len(api_calls_tracker) > API_CALL_LIMIT:
        logging.critical(
            f"CIRCUIT BREAKER TRIPPED! Exceeded {API_CALL_LIMIT} processing attempts in {API_CALL_WINDOW} seconds. Halting daemon."
        )
        send_notification(
            "Daemon.md CRITICAL ERROR", "Runaway process detected. Daemon halted."
        )
        # Forcefully exit the entire process to stop the loop
        os._exit(1)


def process_raw_file(file_path):
    """Wrapper that calls core processing and handles archiving or moving to failed dir."""
    check_circuit_breaker()

    file_path = Path(file_path)
    success, actions = process_file_core(file_path)
    if success:
        # Move to archive directory
        try:
            archive_path = (
                ARCHIVE_DIR / f"{file_path.stem}_{int(time.time())}{file_path.suffix}"
            )
            shutil.move(str(file_path), str(archive_path))
            logging.info(f"Archived processed file to {archive_path}")

            # --- NEW: APPEND TO CONTINUOUS LOG ---
            try:
                now = datetime.datetime.now()
                timestamp = now.strftime("%Y%m%d_%H%M%S")
                log_path = VAULT_DIR / "log.md"

                with daemon_write_lock:
                    # Implement Monthly Rotation
                    if log_path.exists():
                        # Get modification time of current log to check its month
                        mtime = datetime.datetime.fromtimestamp(
                            log_path.stat().st_mtime
                        )
                        if mtime.year != now.year or mtime.month != now.month:
                            # It's a new month, rotate the log
                            logs_archive_dir = ARCHIVE_DIR / "logs"
                            logs_archive_dir.mkdir(parents=True, exist_ok=True)
                            archived_log_path = (
                                logs_archive_dir / f"log_{mtime.strftime('%Y_%m')}.md"
                            )
                            shutil.move(str(log_path), str(archived_log_path))
                            logging.info(
                                f"Rotated continuous ledger to {archived_log_path}"
                            )

                log_entry = f"- **[{timestamp}]** Ingested: {file_path.name}\n"
                for action in actions:
                    log_entry += f"  - {action}\n"
                with daemon_write_lock:
                    with open(log_path, "a", encoding="utf-8") as log_file:
                        log_file.write(log_entry)
            except Exception as e:
                logging.error(
                    f"Failed to append to log.md for {file_path.name}: {e}",
                    exc_info=True,
                )

        except Exception as e:
            logging.error(
                f"Failed to move {file_path.name} to archive directory: {e}",
                exc_info=True,
            )
            move_to_failed(file_path)
    else:
        move_to_failed(file_path)


processing_files = set()
processing_lock = threading.Lock()


def safe_process_raw_file(file_path):
    """Wrapper to prevent duplicate processing of the same file."""
    path_str = str(file_path)

    # Immediately drop queued events for files that were already processed and moved
    if not Path(path_str).exists():
        return

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


def is_rebuild_in_progress():
    return (VAULT_DIR / ".rebuild_lock").exists()


def handle_file_async(file_path):
    """Wait briefly, then process the file. This runs in a worker thread."""
    if is_rebuild_in_progress():
        return
    time.sleep(1)
    safe_process_raw_file(file_path)


debounce_timers: Dict[str, threading.Timer] = {}
debounce_lock = threading.Lock()


def _process_debounced_wiki_edit(file_path):
    """The actual worker function that runs after the debounce timer finishes."""
    path_str = str(file_path)
    file_path = Path(file_path)

    if is_rebuild_in_progress():
        return

    logging.info(f"Manual edit detected and debounced in wiki: {file_path.name}")

    try:
        # Copy the edited file into the raw directory to trigger the Self-Feedback Loop
        dest_path = RAW_DIR / f"manual_edit_{int(time.time())}_{file_path.name}"
        # Use standard read/write loop to avoid iCloud macOS `fcopyfile` deadlocks
        with open(file_path, "rb") as src, open(dest_path, "wb") as dst:
            shutil.copyfileobj(src, dst)
        logging.info(f"Copied manual edit to {dest_path} for ingestion.")
    except Exception as e:
        logging.error(
            f"Failed to capture manual edit for {file_path.name}: {e}", exc_info=True
        )

    # Clean up the timer reference
    with debounce_lock:
        if path_str in debounce_timers:
            del debounce_timers[path_str]


def handle_wiki_edit_async(file_path):
    """Debounces manual edits to prevent rapid-fire auto-saves from flooding the daemon."""
    path_str = str(file_path)

    if is_rebuild_in_progress():
        return

    with daemon_write_lock:
        last_written = daemon_written_files.get(path_str, 0)
        # If the daemon wrote this file recently (within 5 seconds), it's the daemon's own event.
        # Check this BEFORE starting the debounce timer.
        if time.time() - last_written < 5:
            return

    with debounce_lock:
        if path_str in debounce_timers:
            debounce_timers[path_str].cancel()

        # Wait 10 seconds for the user to finish typing/auto-saving before copying
        timer = threading.Timer(10.0, _process_debounced_wiki_edit, args=[file_path])
        debounce_timers[path_str] = timer
        timer.start()


class WikiFolderHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if not event.is_directory and Path(event.src_path).suffix.lower() == ".md":
            executor.submit(handle_wiki_edit_async, event.src_path)

    def on_created(self, event):
        if not event.is_directory and Path(event.src_path).suffix.lower() == ".md":
            executor.submit(handle_wiki_edit_async, event.src_path)

    def on_moved(self, event):
        if not event.is_directory and Path(event.dest_path).suffix.lower() == ".md":
            if Path(event.dest_path).is_relative_to(WIKI_DIR):
                executor.submit(handle_wiki_edit_async, event.dest_path)


class RawFolderHandler(FileSystemEventHandler):
    def on_created(self, event):
        if (
            not event.is_directory
            and Path(event.src_path).suffix.lower() in SUPPORTED_EXTENSIONS
        ):
            # Ignore manual_edit files that we just dropped in here so we don't process them twice
            # The periodic scan will pick them up safely if the event fires concurrently
            executor.submit(handle_file_async, event.src_path)

    def on_moved(self, event):
        # Catch files moved/renamed into the directory
        if (
            not event.is_directory
            and Path(event.dest_path).suffix.lower() in SUPPORTED_EXTENSIONS
        ):
            if Path(event.dest_path).parent == RAW_DIR:
                executor.submit(handle_file_async, event.dest_path)

    def on_modified(self, event):
        # Catch files synced via iCloud that may bypass creation events
        if (
            not event.is_directory
            and Path(event.src_path).suffix.lower() in SUPPORTED_EXTENSIONS
        ):
            executor.submit(handle_file_async, event.src_path)


def periodic_scan():
    """Fallback scanner to catch files if filesystem events fail (common on iCloud)."""
    # Prune old entries from daemon_written_files to prevent memory leaks
    now = time.time()
    with daemon_write_lock:
        keys_to_delete = [k for k, ts in daemon_written_files.items() if now - ts > 60]
        for k in keys_to_delete:
            del daemon_written_files[k]

    for file in RAW_DIR.iterdir():
        if file.is_file() and file.suffix.lower() in SUPPORTED_EXTENSIONS:
            safe_process_raw_file(file)


def main():
    logging.info(
        f"Starting Daemon.md watching {RAW_DIR} and {WIKI_DIR} with {POLL_INTERVAL}s polling fallback"
    )

    raw_handler = RawFolderHandler()
    wiki_handler = WikiFolderHandler()

    observer = Observer()
    observer.schedule(raw_handler, str(RAW_DIR), recursive=False)
    observer.schedule(wiki_handler, str(WIKI_DIR), recursive=True)
    observer.start()

    # Process any files that are already in the raw directory on startup
    periodic_scan()

    try:
        while True:
            time.sleep(POLL_INTERVAL)
            periodic_scan()
    except KeyboardInterrupt:
        observer.stop()
    finally:
        executor.shutdown(wait=True)
    observer.join()


if __name__ == "__main__":
    main()
