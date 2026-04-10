# Daemon.md

Daemon.md is a fully autonomous, self-seeding knowledge graph engine that lives entirely inside an Obsidian markdown vault on macOS.

Instead of relying on traditional Retrieval-Augmented Generation (RAG), which searches for context at query time, Daemon.md utilizes an architecture called **Eager Compilation**. When a raw note is dropped into the inbox, a background daemon instantly leverages Google's Gemini models to extract entities, map concepts, and autonomously write interconnected markdown files directly into the vault.

The project also includes a local 3D visualizer to explore the semantic graph in real-time.

---

## Core Capabilities

- **Eager Compilation:** Unstructured `.md` files dropped into the `raw/` inbox are instantly processed, categorized, and rewritten into the permanent knowledge base.
- **Configurable AI Backend:** Powered by the new `google-genai` SDK. Defaults to `gemini-3.1-flash-lite-preview` for low-latency routing and JSON extraction, and `gemini-3.1-pro-preview` for deep weekly synthesis. Models are fully configurable via environment variables.
- **Ghost Nodes:** The engine aggressively uses `[[Wikilinks]]` to connect concepts. If a concept is linked but does not exist in the file system yet, it is tracked as a "Ghost Node," highlighting frontiers of missing knowledge.
- **Latent Space Explorer:** A local Vite and React web application that renders a 3D semantic map of the knowledge graph.
- **Frictionless macOS Integration:** Utilizes native macOS `launchd` for highly reliable, zero-terminal continuous background processing, and `osascript` for native push notifications upon successful ingestion.
- **Resilient Operations:** Features thread-safe duplicate processing prevention, graceful API circuit breakers (moving unparseable files to a `failed/` directory instead of infinite retries), robust rotating logs, and automatic redaction of API keys from all output streams.

---

## Prerequisites

- **macOS:** Required due to reliance on native tools (`launchctl` and `osascript`).
- **Python 3:** Installed and available in your PATH.
- **Node.js & npm:** Required for the 3D visualizer frontend.
- **Google Gemini API Key:** Obtainable via Google AI Studio.

---

## Architecture and Installation

It is critical that the Daemon.md codebase and the Obsidian Vault data remain separated. The scripts should be cloned to a standard directory (e.g., `~/Daemon_Engine`), while the Vault should be hosted in your preferred location (e.g., iCloud Drive).

### Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/daemon-md.git
   cd daemon-md
   ```

2. **Configure Environment:**
   Copy the example config and edit it to include your API key and the absolute path to your Vault.
   ```bash
   cp .env.example .env
   nano .env
   ```
   *Note: Ensure your `VAULT_PATH` is wrapped in quotes if it contains spaces.* The Python backend will automatically handle scrubbing terminal escape characters (like `\ `) common to macOS iCloud paths.

3. **Run the Installer:**
   ```bash
   ./install.sh
   ```
   The `install.sh` script is a zero-terminal setup utility. It performs the following operations:
   - Scaffolds the strict directory structure in the Vault.
   - Generates the master `GEMINI.md` system prompt.
   - Sets up a localized Python virtual environment (`venv`) and installs dependencies.
   - Executes `npm install` for the visualizer.
   - Creates and registers macOS `launchd` `.plist` agents to start the background engine.

---

## Application Components

### 1. The Ingestion Engine (`daemon.py`)
Once installed, the daemon runs continuously as a background process. It utilizes `watchdog` to monitor the `raw/` directory for filesystem creation and modification events. To ensure reliability against silent iCloud synchronization drops, it also performs a lazy polling sweep every 60 seconds.

**Workflow:**
- Drop any unstructured text or meeting note into the `raw/` folder as an `.md` file.
- The daemon reads the note, provides the rest of the vault to Gemini for context, and requests a JSON array of `wiki_updates` or `task_completions`.
- Target files are completely rewritten to weave the new context seamlessly into the old, maintaining Markdown hygiene.
- The raw file is deleted.
- A macOS push notification is fired detailing the updated entities or concepts.

### 2. The Synthesis Linter (`lint_wiki.py`)
A scheduled cron job running automatically every Sunday at 3:00 AM.
It compiles the entire knowledge graph into a single secure XML payload and instructs a reasoning model (defaulting to `3.1-pro`) to audit the vault. It generates a `Maintenance_Report.md` at the root of the vault detailing:
- Logical contradictions.
- Orphaned nodes.
- Unseen synthesis opportunities.
- A checklist of actionable recommendations for the week.

### 3. The Latent Space Explorer (`start_visualizer.sh`)
The `graph_builder.py` script automatically runs after every daemon ingestion and linter execution, generating an updated `latent_space.json` map of the vault.

To view the graph in 3D, run:
```bash
./start_visualizer.sh
```
This spins up a local Vite dev server. Open `http://localhost:5173` in a web browser.
- **Cyan Nodes:** Entities (People, Companies, Hardware)
- **Magenta Nodes:** Concepts (Frameworks, Theories, Projects)
- **Grey Nodes:** Ghost Nodes (Unresolved Wikilinks)

---

## Vault Architecture

The script automatically generates this structure at your designated `VAULT_PATH`:

```text
/Your_Vault/
  ├── GEMINI.md (The master system prompt)
  ├── raw/ (The inbox where new notes are dropped)
  ├── failed/ (Circuit breaker output for unparseable raw notes)
  ├── wiki/
  │   ├── entities/
  │   └── concepts/
  ├── Action_Items/ (Where executable tasks are saved)
  └── Maintenance_Report.md (Generated weekly)
```

### Customizing the AI Behavior
The autonomous extraction behavior is controlled by the `GEMINI.md` file located at the root of the vault. This file is heavily optimized for Gemini 3.1 reasoning models, enforcing Chain-of-Thought processing before markdown generation. You may edit this file to give the daemon new instructions or alter its categorization rules.

---

## Lifecycle Management and Troubleshooting

### Scripts
- **Updating:** Run `./update.sh` to pull the latest code from Git, update dependencies, and gracefully restart the background services.
- **Uninstalling:** Run `./uninstall.sh` to unload the `launchd` background services from the system. This will *not* delete the codebase or the Vault data.
- **Manual Restart:** To manually reload the daemon without pulling code:
  ```bash
  launchctl unload ~/Library/LaunchAgents/com.user.daemon.md.plist
  launchctl load ~/Library/LaunchAgents/com.user.daemon.md.plist
  ```

### Logs and Metrics
- **Application Logs:** All Python application logs (`daemon.log` and `linter.log`) and standard output from `launchd` are centralized in the `logs/` directory. They utilize a `RotatingFileHandler` (capped at 5MB) to ensure stable disk usage.
- **Security:** API keys are automatically redacted from all log streams.
- **Cost Tracking:** The engine records the exact number of Gemini API tokens consumed during every execution. This data is appended to `logs/cost_tracker.jsonl` for observability.

### Ingestion Failures
If a note dropped into `raw/` fails to process—whether due to an API quota limit, network failure, or an unparseable JSON hallucination—the daemon will catch the exception and move the file into the `failed/` directory. This prevents the periodic scanner from infinitely retrying the broken file and draining API credits. You can inspect the file and move it back into `raw/` to retry.
