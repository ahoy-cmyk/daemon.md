# Daemon.md

**Daemon.md** is a fully autonomous, self-seeding knowledge graph engine that lives entirely inside an Obsidian markdown vault on macOS.

Instead of traditional Retrieval-Augmented Generation (RAG) which searches for context *at query time*, Daemon.md uses **"Eager Compilation"**. When you drop a raw note into the inbox, a background daemon instantly uses Google's Gemini models to extract entities, map concepts, and autonomously write interconnected markdown files into your vault.

It includes a native 3D visualizer to explore your semantic graph in real-time.

---

## Features

- 🧠 **Eager Compilation:** Drops unstructured `.md` files into the `raw/` inbox. They are instantly processed, categorized, and rewritten into your permanent wiki.
- ⚡️ **Gemini Powered:** Fully configurable AI backend. Defaults to `gemini-3.1-flash` for lightning-fast routing and JSON extraction, and `gemini-3.1-pro` for deep weekly synthesis.
- 👻 **Ghost Nodes:** Aggressively uses `[[Wikilinks]]` to connect concepts. If a concept is linked but doesn't exist yet, it appears as a "Ghost Node" in your visualizer, showing the frontiers of your knowledge.
- 🌌 **Latent Space Explorer:** A local Vite/React web application rendering a 3D semantic map of your vault.
- 💻 **Frictionless macOS Integration:** Uses native macOS `launchd` for continuous background processing and `osascript` for native push notifications upon updates.

## Prerequisites

- **macOS** (This project utilizes macOS native tools like `launchctl` and `osascript`).
- **Python 3** installed and available in your PATH.
- **Node.js & npm** installed (for the 3D visualizer).
- A **Google Gemini API Key**.

---

## Installation

1. **Clone the repository:**
   Keep this project directory *outside* of your Obsidian Vault (e.g., in `~/Daemon_Engine`). The logic and data should remain separated.
   ```bash
   git clone https://github.com/yourusername/daemon-md.git
   cd daemon-md
   ```

2. **Configure Environment:**
   Copy the example config and edit it to include your Gemini API key and the absolute path to where you want your Vault to live (e.g., in iCloud).
   ```bash
   cp .env.example .env
   nano .env
   ```
   *Note: Ensure your `VAULT_PATH` is wrapped in quotes if it contains spaces (like iCloud drive paths).*

3. **Run the Installer:**
   The `install.sh` script is a zero-terminal setup. It will:
   - Scaffold the folder structure in your Vault.
   - Generate the master `GEMINI.md` system prompt.
   - Set up a Python virtual environment and install dependencies.
   - Run `npm install` for the 3D Visualizer.
   - Create and load macOS `launchd` plists to run the engine in the background.
   ```bash
   ./install.sh
   ```

---

## Usage

### 1. The Ingestion Engine (`daemon.py`)
Once installed, the daemon runs continuously in the background.
Simply drop any new text, brain dump, or meeting note into the `raw/` folder in your Vault as an `.md` file.

Within seconds, you will receive a macOS push notification detailing the concepts, entities, or action items that were updated. The raw file will be deleted, and your permanent wiki will be updated.

### 2. The Synthesis Linter (`lint_wiki.py`)
A weekly cron job automatically runs every Sunday at 3:00 AM. It reads your entire knowledge graph, uses `gemini-3.1-pro` to audit for contradictions, orphaned nodes, and synthesis opportunities, and generates a `Maintenance_Report.md` at the root of your vault.

### 3. The Latent Space Explorer
To visualize your brain in 3D:
```bash
./start_visualizer.sh
```
This spins up a local Vite dev server. Open `http://localhost:5173` to explore.
- 🔵 **Cyan:** Entities (People, Companies, Hardware)
- 🟣 **Magenta:** Concepts (Frameworks, Theories, Projects)
- ⚪️ **Grey:** Ghost Nodes (Unresolved Wikilinks)

---

## Vault Architecture

The script automatically generates this structure at your designated `VAULT_PATH`:

```text
/Your_Vault/
  ├── GEMINI.md (The master system prompt)
  ├── raw/ (The inbox where new notes are dropped)
  ├── failed/ (Where unparseable raw notes are moved)
  ├── wiki/
  │   ├── entities/
  │   └── concepts/
  ├── Action_Items/ (Where executable tasks are saved)
  └── Maintenance_Report.md (Generated weekly)
```

## Customizing the AI

The behavior of the autonomous extraction is controlled entirely by the `GEMINI.md` file located at the root of your vault. You can edit this file at any time to give the daemon new instructions, change how it categorizes data, or update its markdown formatting rules.

## Troubleshooting

- **Logs:** If the background daemon isn't working, check the `logs/` directory. It contains detailed Python application logs (`daemon.log`, `linter.log`) as well as `launchd` service logs.
- **Failed Ingestion:** If a note dropped in `raw/` fails to process due to a parsing error or API limit, it will be moved to the `failed/` directory in your Vault. You can edit the file to fix any obvious issues and move it back to `raw/` to retry.
- **Updating Daemon.md:** To pull the latest code and restart the background services, simply run:
  ```bash
  ./update.sh
  ```
- **Uninstalling:** To remove the background services from your system (this does not delete your Vault or the code):
  ```bash
  ./uninstall.sh
  ```
- **Restarting the Daemon:** If you need to restart the background processes manually, run `./install.sh` again, or use:
  ```bash
  launchctl unload ~/Library/LaunchAgents/com.user.daemon.md.plist
  launchctl load ~/Library/LaunchAgents/com.user.daemon.md.plist
  ```
- **Virtual Environment:** The system uses a local virtual environment located at `./venv`. If Python dependencies fail, try deleting the `./venv` folder and re-running `./install.sh`.
