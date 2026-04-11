# Daemon.md

Daemon.md is a background service that automatically turns your raw notes, thoughts, and voice memos into a structured, interconnected Obsidian wiki.

Inspired by Andrej Karpathy's [LLM Wiki concept](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f), this project moves away from standard RAG (Retrieval-Augmented Generation) databases. Instead, it reads your input, extracts the core concepts, and formally writes actual markdown (`.md`) files directly into your local folder, maintaining a web of `[[Wikilinks]]` for you.

You drop a voice memo into a folder, and seconds later, your notes are updated, cross-referenced, and organized.

*(If you are a developer looking for the technical deep-dive into how the daemon, archiving, and feedback loops work, please read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).)*

---

## Quick Start Guide

### Prerequisites
- **macOS:** Required for the background service and push notifications.
- **Python 3:** Installed and in your PATH.
- **Node.js & npm:** Installed (for the 3D visualizer).
- **Obsidian:** Installed on your Mac.
- **Google Gemini API Key:** Get a free one from [Google AI Studio](https://aistudio.google.com/apikey).

### Step 1: Setup the Engine
The engine code lives in this repository, entirely separate from your actual notes.

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/daemon-md.git
   cd daemon-md
   ```
2. Copy the environment template:
   ```bash
   cp .env.example .env
   ```
3. Open `.env` and fill in your API key and the path where you want your new Obsidian Vault to live:
   ```text
   GEMINI_API_KEY="AIzaSyYourKeyHere..."
   VAULT_PATH="~/Documents/My_AI_Vault"
   ```

### Step 2: Install and Start
Run the installer script:
```bash
./install.sh
```
This script will:
- Check your permissions.
- Build the directory structure in your `VAULT_PATH`.
- Setup a Python virtual environment and install dependencies.
- Register the background service with macOS (`launchd`) so it runs silently forever.

### Step 3: Open Obsidian
1. Open the **Obsidian** app.
2. Click **"Open folder as vault"**.
3. Select the folder you defined in your `VAULT_PATH` and click **Open**.

You are now ready to go!

---

## How to Use It (Day-to-Day)

### 1. Ingesting Raw Notes and Audio
Inside your Vault, you will see a folder called `raw/`.
This is your inbox.

If you write a quick thought in a `.txt` file, or record a voice memo on your iPhone (`.m4a`) and drop it into the `raw/` folder, the background Daemon will immediately wake up. It will upload the file, transcribe it, analyze it against your existing wiki, and write new or updated markdown files into your `wiki/` folder. You will get a macOS push notification when it is done.

### 2. Manual Edits
You are not locked out of your own notes. If the AI generates a concept page and you want to fix a typo, add a paragraph, or write a completely new page yourself—just do it.

When you type and save a file inside the `wiki/` folder, the Daemon notices. It automatically copies your manual edit back into the `raw/` inbox. This forces the AI to ingest your human thoughts and formally integrate them into the overall knowledge graph.

### 3. The Source of Truth (Archiving)
When the Daemon processes a file from the `raw/` folder, it does not delete it. It moves the original file into the `archive/` folder. This means you never lose your original voice memos or unedited notes.

### 4. Customizing the AI (GEMINI.md)
Inside your Vault, you will find a file named `GEMINI.md`. This is the **Master Prompt** for the system.
Every time the Daemon processes a note, it reads `GEMINI.md` to understand how it should behave.
You can edit this file to give the AI custom instructions. For example, you can tell it to use a specific tone, categorize notes into new folders, or look out for specific keywords (e.g., "If I mention 'Groceries', always add it to a checklist").

---

## Available Commands

This repository includes several bash scripts to help you manage the system. Run these from the `daemon-md` directory:

- `./status.sh`
  Checks if the background daemon is running, shows you how many API tokens you've used (and the cost), and prints the latest logs.

- `./start_visualizer.sh`
  Starts a local web server (on `localhost:5173`). Open this in your browser to see a 3D, interactive map of your entire knowledge graph. It highlights "Ghost Nodes" (concepts the AI linked to, but hasn't fully written a page for yet).

- `python rebuild.py`
  Because your original notes are saved in the `archive/`, you can rebuild the entire system from scratch. This script warns you, wipes the generated wiki, and feeds your entire history back through the Daemon. Use this in a year when a much smarter AI model is released to retroactively upgrade all your old notes.

- `./update.sh`
  Pulls the latest code from GitHub and safely restarts the background services.

- `./uninstall.sh`
  Stops the background services and removes them from macOS. (This does *not* delete your Obsidian Vault or your notes).
