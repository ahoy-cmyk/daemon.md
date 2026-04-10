# Daemon.md: The Eager Compilation Knowledge Engine

Daemon.md is an enterprise-grade, fully autonomous, self-seeding knowledge graph engine that lives entirely inside your local Obsidian markdown vault on macOS.

Traditional AI workflows rely on **Retrieval-Augmented Generation (RAG)**—where a massive, unstructured database is searched only at the exact moment you ask a query. RAG is passive; it requires you to know what you are looking for, and its accuracy is bound by the quality of its vector search.

Daemon.md introduces a fundamentally different architecture: **Eager Compilation**.
When you drop a raw, messy note into the inbox, a background macOS daemon instantly activates. It leverages the latest reasoning models (Google Gemini 3.1 via the `google-genai` SDK) to structurally extract entities, map concepts, and autonomously write pristine, interconnected markdown files directly into your permanent vault. Knowledge is synthesized, linked, and organized *the moment it is ingested*.

Your vault is no longer a graveyard of unread notes. It is a living, breathing semantic engine.

---

## I. Architectural Philosophy & Core Capabilities

Daemon.md is built strictly around the separation of logic and data. The execution engine (Python scripts, bash utilities, Node.js visualizer) sits entirely outside of your markdown vault, acting upon it via absolute paths.

### 1. Eager Ingestion (The Daemon)
A highly optimized Python background process (`daemon.py`) monitors a designated `raw/` inbox directory. It uses `watchdog` to catch filesystem creation events, augmented by an `on_modified` handler to capture silent iCloud drive synchronizations (e.g., notes typed on your iPhone). A battery-friendly 60-second lazy sweep acts as a final fail-safe.

When a note is detected:
1. The daemon reads the note and fetches the current 3D structural map of your vault (`latent_space.json`).
2. It sends this context to `gemini-3.1-flash-lite-preview`.
3. The LLM utilizes native JSON-mode to output highly structured instructions, classifying the knowledge as an Entity, a Concept, or an Action Item.
4. Target markdown files in your vault are **completely rewritten** to weave the new context seamlessly into the old, preventing the fragmentation of appended text.
5. A native macOS push notification is fired, and the raw note is deleted.

### 2. The Latent Space Explorer (Ghost Nodes)
Eager Compilation relies heavily on Obsidian-style `[[Wikilinks]]`. The engine is strictly instructed to link concepts even if they do not exist yet.

After every ingestion, the `graph_builder.py` script traverses the vault and generates a structural JSON map. If an entity is referenced but has no markdown file, it is instantiated as a **Ghost Node**.

By running `./start_visualizer.sh`, you spin up a local Vite/React web application leveraging Three.js (`react-force-graph-3d`) to explore this map. You can visually identify Ghost Nodes (rendered in dim grey), instantly highlighting the frontiers of your missing knowledge.

### 3. The Synthesis Linter (Cron Job)
A weekly scheduled macOS `launchd` task runs every Sunday at 3:00 AM. `lint_wiki.py` recursively packages your entire knowledge graph into a secure XML payload and submits it to `gemini-3.1-pro-preview`. The model audits the graph to generate a `Maintenance_Report.md` detailing logical contradictions, orphaned nodes, synthesis opportunities, and a checklist of actionable improvements for the week.

---

## II. Security, Performance, and Resilience

This engine is designed to run indefinitely in the background without user intervention. It includes several enterprise-grade stability features:

- **Idempotent Caching:** The installation and update scripts (`install.sh`, `update.sh`) utilize SHA-1 hash caching for both `requirements.txt` and `package.json`. Dependencies are only installed if they have changed, making updates instantaneous.
- **Context Window Optimization:** Rather than sending the entire multi-megabyte textual contents of your vault to the LLM on every minor note ingestion—which causes severe latency and burns massive API tokens—the daemon passes the lightweight `latent_space.json` map. The model understands the structure of your brain without reading every word.
- **Thread Safety:** Watchdog events and periodic scanning loops are guarded by a `threading.Lock()` to prevent race conditions or duplicate API calls if a file is triggered twice simultaneously.
- **API Circuit Breaker:** If a note fails to process due to a quota limit, network error, or a hallucinated JSON structure from the LLM, the file is immediately moved to a `failed/` directory. This prevents the daemon from infinitely retrying a broken file and draining your API budget.
- **Log Redaction:** A custom `APIRedactingFormatter` sits inside the Python `logging` module. Every single log message and traceback is intercepted, and any instance of your `GEMINI_API_KEY` is scrubbed and replaced with `***REDACTED_API_KEY***`.
- **Command Injection Prevention:** Terminal escape characters (like `\ `) common to macOS iCloud paths are scrubbed natively in Python. The installer uses strict parameter expansion (`${VAULT_PATH/#\~/$HOME}`) rather than `eval`, neutralizing arbitrary shell command execution. AppleScript push notifications are rigorously escaped.

---

## III. Setup and Installation

### Prerequisites
- **macOS:** Required due to reliance on native tools (`launchctl` and `osascript`).
- **Python 3:** Installed and available in your PATH.
- **Node.js & npm:** Required for the 3D Latent Space visualizer.
- **Google Gemini API Key:** Obtainable via [Google AI Studio](https://aistudio.google.com/apikey).

### Installation Instructions

1. **Clone the Engine:**
   Keep the engine separated from your Vault (e.g., in `~/Daemon_Engine`).
   ```bash
   git clone https://github.com/yourusername/daemon-md.git
   cd daemon-md
   ```

2. **Configure the Environment:**
   ```bash
   cp .env.example .env
   nano .env
   ```
   Add your Gemini API key and the absolute path to your Obsidian vault. *Note: Ensure your `VAULT_PATH` is wrapped in quotes if it contains spaces.* The Python backend will automatically handle the resolution.

3. **Run the Installer:**
   ```bash
   ./install.sh
   ```
   This script features a beautifully colorized UI. It tests macOS Full Disk Access write privileges, scaffolds the directory structure in your Vault, generates the `GEMINI.md` master prompt, creates a localized Python `venv`, runs `npm install`, and registers the background services with `launchctl`.

---

## IV. Command Line Interface (CLI) Utilities

Daemon.md includes an ANSI-colorized suite of bash utilities for lifecycle management.

### 1. The Status Dashboard (`./status.sh`)
Run this at any time to view a live, beautiful terminal dashboard. It parses `launchctl` to verify your background services are alive, instantly calculates your total API token consumption from the metrics tracker, and prints the most recent log events.

### 2. The Updater (`./update.sh`)
A safe, 1-click update mechanism. It checks for uncommitted changes, stashes them, pulls the latest code from Git, prints a mini-changelog of what is being updated, pops the stash, and runs the idempotent installer to silently reload your background services.

### 3. The Visualizer (`./start_visualizer.sh`)
Spins up the local Vite dev server. Open `http://localhost:5173` to explore your Latent Space graph in 3D.

### 4. The Uninstaller (`./uninstall.sh`)
Safely unloads and removes the `launchd` plist files from the macOS system layer. It does **not** delete your codebase or your Vault.

---

## V. Advanced Configuration

### Customizing the AI Prompt
The autonomous extraction behavior is controlled entirely by the `GEMINI.md` file located at the root of your vault. The scaffolded prompt is highly optimized for the Gemini 3.1 reasoning architecture, enforcing Chain-of-Thought processing before markdown generation. You may edit this file inside Obsidian at any time to give the daemon new instructions or alter its categorization rules.

### Modifying the AI Models
By default, the engine relies on the absolute newest Google AI models. You can override these defaults by editing your `.env` file:
- `GEMINI_MODEL_DAEMON="gemini-3.1-flash-lite-preview"`
- `GEMINI_MODEL_LINTER="gemini-3.1-pro-preview"`

### Monitoring API Costs
Every time the Daemon or Linter communicates with Google, it extracts the exact `prompt_tokens`, `candidates_tokens`, and `total_tokens` consumed. This data is structured as JSON Lines and appended to `logs/cost_tracker.jsonl`. You can read this file programmatically or view the aggregate usage via `./status.sh`.

### Reviewing Application Logs
All standard output and Python application logs (`daemon.log`, `linter.log`) are centralized in the `logs/` directory. They utilize a `RotatingFileHandler` capped at 5MB, ensuring stable long-term disk usage on your Mac.
