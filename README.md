# Daemon.md: Event-Driven Knowledge Compilation

Daemon.md is an autonomous background engine designed to natively structure markdown notes inside a local Obsidian vault on macOS.

Daemon.md replaces the reactive Retrieval-Augmented Generation (RAG) model with a proactive architecture known as **Eager Compilation**. Instead of relying on vector search at query time, the engine relies on immediate, deterministic transformation at ingestion time.

When a raw `.md` file enters the inbox, a background `launchd` process leverages Google's Gemini API to analyze the text, map concepts to a local structural JSON representation, and autonomously write interconnected markdown files directly into the user's permanent file hierarchy.

---

## I. Core Architecture

The Daemon.md system maintains a strict separation of logic and data. The execution engine (Python backend, Bash lifecycle utilities, Node.js visualizer) operates outside the vault boundaries, targeting the local directory via absolute paths to prevent repository pollution.

### 1. The Ingestion Engine (`daemon.py`)
A continuous Python process monitoring the `raw/` inbox directory. It uses the `watchdog` library to capture filesystem `on_created` events, supplemented by an `on_modified` handler to capture silent remote synchronizations (e.g., iCloud Drive). A 60-second polling sweep ensures eventual consistency if `FSEvents` are dropped by the OS.

**Workflow:**
1. A raw note is detected and locked via `threading.Lock()` to prevent race conditions.
2. The daemon loads `latent_space.json`, providing the LLM with the complete structural topology of the vault without the token overhead of reading raw file contents.
3. The context is routed to `gemini-3.1-flash-lite-preview`. The model natively outputs a structured JSON array, routing the analyzed data into three categories: Entities, Concepts, or Action Items.
4. Target markdown files are completely rewritten to integrate the new context, avoiding fragmented append operations.
5. The raw note is deleted, and a native macOS push notification is dispatched via `osascript`.

### 2. The Synthesis Linter (`lint_wiki.py`)
A `launchd` scheduled task (cron) executing every Sunday at 3:00 AM.
The script recursively packages the entire knowledge graph into a secure XML `<vault_content>` payload and routes it to `gemini-3.1-pro-preview`. The reasoning model audits the graph structure and writes a `Maintenance_Report.md` to the vault root containing:
- Logical contradictions detected across files.
- Orphaned nodes requiring integration.
- Structural synthesis opportunities.

### 3. The Latent Space Explorer (`start_visualizer.sh`)
Eager Compilation relies heavily on Obsidian-style `[[Wikilinks]]`. If the LLM generates a wikilink for a concept that does not currently possess a corresponding `.md` file, the engine classifies it as an unresolved **Ghost Node**.

Following every ingestion or lint cycle, `graph_builder.py` parses the vault and generates a deterministic `latent_space.json` map. Running the Vite/React visualizer (`react-force-graph-3d`) renders this topology in a 3D interface, explicitly highlighting Ghost Nodes to identify missing knowledge frontiers.

---

## II. Security, Resilience, and Performance

The application is engineered to run indefinitely as a local service, implementing several strict fault-tolerance and security mechanisms:

- **Idempotent Setup:** The `install.sh` and `update.sh` lifecycle scripts utilize SHA-1 hash caching against `requirements.txt` and `package.json`. Package managers are invoked strictly when dependencies change, optimizing execution time.
- **Context Optimization:** By supplying the LLM with `latent_space.json` rather than recursively feeding the vault contents during ingestion, API token consumption and request latency are radically reduced.
- **Circuit Breakers:** If note processing fails due to network disruption, API quota limits, or invalid JSON schemas from the LLM, the raw file is moved to a `failed/` directory. This mitigates infinite retry loops and prevents API credit exhaustion.
- **Token Tracking:** The application extracts `usage_metadata` from every Google API response, appending `prompt_tokens` and `candidates_tokens` to `logs/cost_tracker.jsonl` for deterministic cost auditing.
- **Log Redaction:** A custom `APIRedactingFormatter` intercepts all output within the Python `logging` module, automatically scrubbing the user's `GEMINI_API_KEY` from disk logs and standard output streams.
- **Injection Defenses:** Terminal escape characters associated with macOS iCloud paths are stripped natively. Shell scripts utilize bash parameter expansion (`${VAULT_PATH/#\~/$HOME}`) rather than `eval` to neutralize command injection. AppleScript notifications rigorously escape shell variables.

---

## III. Setup and Installation

### Prerequisites
- **macOS:** Required for `launchctl` and `osascript` compatibility.
- **Python 3:** Required in `PATH`.
- **Node.js & npm:** Required for the Vite visualizer.
- **Google Gemini API Key:** Obtainable via [Google AI Studio](https://aistudio.google.com/apikey).

### Deployment

1. **Clone the Repository:**
   Maintain the engine directory separately from the Obsidian Vault.
   ```bash
   git clone https://github.com/yourusername/daemon-md.git
   cd daemon-md
   ```

2. **Configure Environment:**
   ```bash
   cp .env.example .env
   nano .env
   ```
   Provide the absolute path to your Obsidian vault. *Paths containing spaces must be wrapped in double quotes.*

3. **Initialize System:**
   ```bash
   ./install.sh
   ```
   The installer validates macOS Full Disk Access permissions, scaffolds the target vault directory structure, generates the `GEMINI.md` system instruction file, instantiates a local Python `venv`, and registers the `launchd` property list (`.plist`) agents.

4. **Connect to Obsidian:**
   - Open the **Obsidian** app on your Mac.
   - Select **"Open folder as vault"**.
   - Navigate to your designated `VAULT_PATH` and click **Open**.
   - You can now drag and drop raw notes directly into the `raw/` folder within the Obsidian interface to trigger the Daemon.

---

## IV. Lifecycle Management (CLI)

The repository provides modular bash utilities for system administration.

- `./status.sh`: Parses `launchctl` to verify daemon health, aggregates total token consumption from `cost_tracker.jsonl`, and outputs the latest rolling logs to the terminal.
- `./update.sh`: Manages safe Git pulls (stashing uncommitted state), outputs a revision changelog, and invokes the idempotent installer to refresh dependencies and reload `launchd` services.
- `./start_visualizer.sh`: Initiates the local Vite server on `localhost:5173` to render the 3D topology.
- `./uninstall.sh`: Unloads and destroys the system `launchd` `.plist` files. It does not modify or delete the local repository or the target Vault.

---

## V. Advanced Configuration

### Autonomous Extraction (GEMINI.md)
The taxonomy and behavioral logic of the Daemon are controlled entirely by the `GEMINI.md` file located at the vault root. The default prompt is optimized for Gemini 3.1 architecture, instructing the model to utilize Chain-of-Thought processing prior to output generation. Modifying this file alters the Daemon's parsing and structural routing behavior dynamically.

### Target Models
The engine relies on the Google GenAI SDK. Default models are defined in `.env.example` and can be overridden:
- `GEMINI_MODEL_DAEMON="gemini-3.1-flash-lite-preview"`
- `GEMINI_MODEL_LINTER="gemini-3.1-pro-preview"`

### Logging
Output streams from both the Python application and the macOS `launchd` service are routed to the `logs/` directory. Files (`daemon.log`, `linter.log`) utilize a `RotatingFileHandler` constrained to 5MB, maintaining a deterministic disk footprint over long-term operation.
