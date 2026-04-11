# 🤖 Agent Instructions for Daemon.md

Welcome to the Daemon.md project! If you are an autonomous AI or coding assistant working on this repository, please read these guidelines carefully.

## 🏛️ Core Architecture: Eager Compilation vs RAG
This project does **not** use standard RAG (Retrieval-Augmented Generation) or vector databases. Instead, it uses **Eager Compilation**.
- **Ingestion:** Raw notes and audio are processed immediately by a background daemon (`daemon.py`).
- **Graph Generation:** The model natively outputs structured JSON mapped directly to the local vault's directory structure, outputting actual interconnected markdown (`.md`) files.
- **Context:** To avoid blowing up API costs, we feed the LLM a structural JSON representation (`latent_space.json`) of the entire vault, rather than recursively sending thousands of markdown files.

## 🗂️ File Archiving & Rebuild Logic
- When a file drops into `VAULT_PATH/raw`, `daemon.py` processes it.
- **Crucial:** Upon successful processing, raw files (both text and raw audio) are **NOT deleted**. They are moved to the `VAULT_PATH/archive` directory with a timestamp appended to prevent overwrites.
- The `archive/` folder acts as the ultimate "source of truth".
- **Rebuilds:** The `rebuild.py` script is used to perform a full system rebuild if the underlying AI model changes or the user wants to re-process history. It safely wipes the `wiki/`, `Action_Items/`, and `latent_space.json`, and feeds every file in `archive/` sequentially through `process_file_core()` in `daemon.py`.
- **Do not** modify the `rebuild.py` script to duplicate `daemon.py`'s API/Gemini processing logic. It must always import `process_file_core` to stay DRY and future-proof.
- Tools like `lint_wiki.py` and `graph_builder.py` only care about the generated content in the `wiki/` directory. They must continue to ignore the `archive/` and `raw/` directories.

## ✍️ Manual Edits & The Self-Feedback Loop
- To allow the user to write their own notes or manually edit AI-generated files without losing those edits during a rebuild, we employ a **"Self-Feedback Loop"**.
- `daemon.py` actively watches the `wiki/` directory. If it detects a file was created or modified by the user (ignoring its own programmatic writes), it automatically copies that modified file into the `raw/` directory.
- This forces the system to treat manual edits as "new raw input". The AI digests the manual edit, formalizes it, and the raw copied file is placed into `archive/`.
- **Result:** Manual edits become part of the archived source of truth, meaning they will be perfectly preserved and re-integrated during a system rebuild.

## 🔒 Environment & Permissions
- The Python execution engine runs completely outside of the target Obsidian vault directory to prevent polluting it.
- We heavily rely on absolute paths derived from the user's `.env`.
- **Security:** iCloud sync paths can cause macOS `Resource deadlock avoided` errors or file locking issues. Always use robust copy/read/unlink loops with `try/except OSError` blocks (as seen in `daemon.py`) rather than assuming immediate file availability.
- All Google API usage is logged and tracked locally for cost monitoring. Always ensure the API keys are scrubbed from log files using the custom `APIRedactingFormatter`.

## 📦 External Dependencies
- Backend: Python 3, `google-genai` SDK, `watchdog` (for file system events).
- Frontend Visualizer: Node.js, `npm`, Vite, `react-force-graph-3d`. Use standard `npm`, no Bun or pnpm.
- System Integration: macOS `launchd` for background tasks, `osascript` for native push notifications.

Please follow these architectural constraints carefully when making modifications or adding new features!
