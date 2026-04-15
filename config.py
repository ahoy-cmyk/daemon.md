import os
import sys
from pathlib import Path
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).parent.resolve()
load_dotenv(SCRIPT_DIR / ".env")

VAULT_PATH_RAW = os.getenv("VAULT_PATH")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not VAULT_PATH_RAW or not GEMINI_API_KEY:
    print("Error: VAULT_PATH and GEMINI_API_KEY must be set in .env")
    sys.exit(1)

CLEANED_VAULT_PATH = (
    VAULT_PATH_RAW.replace("\\ ", " ")
    .replace("\\~", "~")
    .replace('\\"', '"')
    .replace("\\'", "'")
)

VAULT_DIR = Path(CLEANED_VAULT_PATH).expanduser().resolve()
RAW_DIR = VAULT_DIR / "raw"
ARCHIVE_DIR = VAULT_DIR / "archive"
WIKI_DIR = VAULT_DIR / "wiki"
FAILED_DIR = VAULT_DIR / "failed"
GEMINI_MD_PATH = VAULT_DIR / "GEMINI.md"
REPORT_PATH = VAULT_DIR / "Maintenance_Report.md"

SUPPORTED_EXTENSIONS = {".md", ".txt", ".m4a", ".mp3", ".wav", ".ogg", ".flac", ".aac"}

RAW_DIR.mkdir(parents=True, exist_ok=True)
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
WIKI_DIR.mkdir(parents=True, exist_ok=True)
FAILED_DIR.mkdir(parents=True, exist_ok=True)
