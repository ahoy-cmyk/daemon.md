import os
import sys
import shutil
import logging
from pathlib import Path
from dotenv import load_dotenv

# Import core processing from daemon.py
import daemon
from daemon import ARCHIVE_DIR, VAULT_DIR, FAILED_DIR, SUPPORTED_EXTENSIONS

# Basic logging setup for the script
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

def confirm_rebuild():
    print("\n" + "="*50)
    print("⚠️  WARNING: FULL REBUILD INITIATED ⚠️")
    print("="*50)
    print("This action will:")
    print("1. DELETE all contents of wiki/")
    print("2. DELETE all contents of Action_Items/")
    print("3. DELETE visualizer/public/latent_space.json")
    print("4. Re-process ALL files currently in archive/")
    print("\nThis cannot be undone. Are you sure you want to proceed?")

    response = input("Type 'Y' to confirm, or any other key to abort: ").strip()
    return response == 'Y'

def clear_directory(dir_path: Path):
    if not dir_path.exists():
        return
    for item in dir_path.iterdir():
        if item.is_file():
            item.unlink()
        elif item.is_dir():
            shutil.rmtree(item)

def clear_generated_content():
    logging.info("Clearing existing generated content...")

    wiki_dir = VAULT_DIR / "wiki"
    action_items_dir = VAULT_DIR / "Action_Items"
    latent_space = Path("visualizer/public/latent_space.json")

    # Clear directories
    clear_directory(wiki_dir)
    clear_directory(action_items_dir)

    # Recreate essential subdirectories
    (wiki_dir / "entities").mkdir(parents=True, exist_ok=True)
    (wiki_dir / "concepts").mkdir(parents=True, exist_ok=True)
    action_items_dir.mkdir(parents=True, exist_ok=True)

    # Delete latent space
    if latent_space.exists():
        latent_space.unlink()

    # Re-initialize graph structure
    import graph_builder
    graph_builder.build_graph()

def rebuild():
    if not ARCHIVE_DIR.exists():
        logging.error(f"Archive directory {ARCHIVE_DIR} does not exist.")
        sys.exit(1)

    archived_files = [f for f in ARCHIVE_DIR.iterdir() if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS]

    if not archived_files:
        logging.info("No files found in archive directory to process.")
        return

    # Sort files by timestamp to process in chronological order if possible.
    archived_files.sort(key=lambda x: x.stat().st_mtime)

    logging.info(f"Found {len(archived_files)} files in archive. Starting rebuild...")

    success_count = 0
    fail_count = 0

    for file_path in archived_files:
        logging.info(f"Re-processing: {file_path.name}")
        # Note: We pass is_rebuild=True to skip file size/wait checks since files are fully written
        success = daemon.process_file_core(file_path, is_rebuild=True)
        if success:
            success_count += 1
        else:
            fail_count += 1
            logging.error(f"Failed to process {file_path.name} during rebuild.")

    logging.info("="*50)
    logging.info("Rebuild Complete!")
    logging.info(f"Successfully processed: {success_count}")
    logging.info(f"Failed to process: {fail_count}")
    logging.info("="*50)

if __name__ == "__main__":
    if confirm_rebuild():
        clear_generated_content()
        rebuild()
    else:
        print("Rebuild aborted.")
