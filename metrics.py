import json
import logging
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent.resolve()
LOGS_DIR = SCRIPT_DIR / "logs"
TRACKER_FILE = LOGS_DIR / "cost_tracker.jsonl"


def track_usage(script_name, model_name, usage_metadata):
    """
    Logs token usage data from the Gemini API response to a JSON Lines file.
    usage_metadata is typically response.usage_metadata
    """
    if not usage_metadata:
        logging.warning("No usage metadata provided to track_usage.")
        return

    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)

        # Extract token counts
        prompt_tokens = getattr(usage_metadata, "prompt_token_count", 0)
        candidates_tokens = getattr(usage_metadata, "candidates_token_count", 0)
        total_tokens = getattr(usage_metadata, "total_token_count", 0)

        record = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "script": script_name,
            "model": model_name,
            "prompt_tokens": prompt_tokens,
            "candidates_tokens": candidates_tokens,
            "total_tokens": total_tokens,
        }

        with open(TRACKER_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    except Exception as e:
        logging.error(f"Failed to write to cost tracker: {e}")
