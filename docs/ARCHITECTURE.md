# Daemon.md Architecture

This document is a comprehensive, exhaustive technical deep-dive into the architecture of Daemon.md. It is intended for developers, maintainers, and technically curious users who want to understand exactly how the system operates under the hood.

---

## 1. The Core Concept: Eager Compilation vs. RAG

Daemon.md was directly inspired by the "LLM Wiki" concept [proposed by Andrej Karpathy](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

Most modern AI knowledge systems rely on **Retrieval-Augmented Generation (RAG)**:
- You upload documents.
- The system chunks the text, runs it through an embedding model, and saves it to a vector database.
- When you ask a question, it retrieves chunks of text via similarity search and formulates an answer on the fly.
- **The RAG Flaw:** It rediscovers knowledge from scratch every time. It struggles with holistic synthesis because the knowledge only exists as fragmented math in a database.

Daemon.md replaces RAG with **Eager Compilation**:
- **Ingestion Time, Not Query Time:** When a raw file drops into the system, the LLM reads it immediately. It doesn't index it; it actually writes it into interconnected, human-readable markdown files (`.md`).
- **A Compiled Wiki:** The LLM does the tedious bookkeeping humans hate. It creates dedicated entity pages, updates concepts, flags contradictions, and maps out a localized web of knowledge connected by Obsidian `[[Wikilinks]]`.
- **The Result:** The knowledge base is fully compiled on your hard drive. The cross-references are already there. The knowledge compounds and gets richer with every source you add, acting as a true "second brain".

---

## 2. Vault Directory Structure

Daemon.md strictly separates the execution logic (Python scripts, Node.js visualizer) from your data. The codebase lives in its own repository, while the engine operates on a target Obsidian Vault directory.

When initialized, Daemon.md scaffolds the following structure inside your Vault:

```text
Your_Obsidian_Vault/
│
├── raw/                  # The Inbox. Drop text notes and voice memos here.
├── archive/              # The Source of Truth. Raw files are moved here after processing.
├── failed/               # The Quarantine. Unparseable files go here to prevent retry loops.
│
├── wiki/                 # The Compiled Knowledge Graph (Managed by the AI).
│   ├── entities/         # Pages for people, places, companies, tools.
│   └── concepts/         # Pages for abstract ideas, frameworks, theories.
│
├── Action_Items/         # Executable tasks extracted from your notes.
│
├── GEMINI.md             # The master prompt controlling the AI's behavior.
└── Maintenance_Report.md # Generated weekly by the Synthesis Linter.
```

---

## 3. System Components & Data Flow

### 3.1. The Ingestion Engine (`daemon.py`)
This is the heart of the system—a continuous Python background process monitoring the `raw/` directory.

- **Event Watching:** Uses the `watchdog` library to capture filesystem `on_created` events.
- **Polling Fallback:** Features a configurable fallback polling sweep (`DAEMON_POLL_INTERVAL`) to catch silent sync events from cloud providers like iCloud Drive that often drop FSEvents.
- **Audio Processing:** Natively processes audio files (e.g., iPhone Voice Memos in `.m4a`, `.mp3`, `.wav`). It securely uploads the audio to the Gemini API for native transcription and analysis, then explicitly deletes the remote file in a `finally` block to prevent storage leaks.
- **Context Optimization:** Feeding a massive vault of markdown files to an LLM on every ingestion is prohibitively expensive and slow. Instead, the daemon feeds the LLM `latent_space.json`—a lightweight structural map of the vault. The LLM uses this map to know what concepts already exist and where to route new information.
- **Strict Formatting:** The LLM is instructed via `GEMINI.md` to output a strict JSON array. Each object dictates the target file path and the complete markdown content. The python script then writes these files to disk.

### 3.2. File Archiving & Full System Rebuilds (`rebuild.py`)
The system preserves history to future-proof your knowledge.

- **The Archive:** When `daemon.py` successfully ingests a raw file, it does not delete it. It moves it to the `archive/` directory with a timestamp appended to the filename. This creates an immutable, unindexed source of truth.
- **Rebuilds:** The AI models we use today will be obsolete in a few years. The `rebuild.py` script allows users to completely wipe their generated `wiki/` and `Action_Items/` directories, and sequentially feed the entire `archive/` history back into the system. This allows the vault to be retroactively upgraded, applying newer, smarter intelligence to all historical data.

### 3.3. Manual Edits and The Self-Feedback Loop
The wiki is not exclusively AI-generated. Users must be able to write their own notes or manually fix typos in AI-generated notes without losing those edits during a system rebuild.

- `daemon.py` utilizes a `WikiFolderHandler` to actively watch the generated `wiki/` directory.
- To prevent infinite loops, the daemon maintains a `daemon_written_files` dictionary in memory. If the daemon writes a file, it ignores the resulting filesystem event.
- If a human edits or creates a file in the `wiki/`, the handler detects it and secretly copies that modified file back into the `raw/` directory with a `manual_edit_` prefix.
- The AI digests the human edit, formalizes it, and the raw copied file is placed into `archive/`. Therefore, manual edits become part of the immutable history and survive future rebuilds.

### 3.4. The Synthesis Linter (`lint_wiki.py`)
A background cron job (scheduled via a macOS `launchd` `.plist` file for Sunday nights).
- It packages the entire text of the `wiki/` into a secure XML `<vault_content>` payload.
- It asks a reasoning model (default: `gemini-3.1-pro-preview`) to audit the entire graph.
- It produces a `Maintenance_Report.md` at the vault root, detailing logical contradictions across notes, orphaned nodes, and high-level synthesis opportunities.

### 3.5. Latent Space Mapping (`graph_builder.py`)
After every single ingestion or linting cycle, this script scans the `wiki/` directory.
- It parses all markdown files, looking for `[[Wikilinks]]`.
- It generates a deterministic JSON map (`latent_space.json`) of nodes and edges.
- **Ghost Nodes:** If it finds a wikilink pointing to a concept that does not have a dedicated markdown file yet, it creates a "Ghost Node" in the JSON.
- This JSON is consumed by both the Python Backend (to give the LLM structural context) and the Node.js Frontend (for 3D visualization).

---

## 4. Environment, Security, and Edge Cases

Daemon.md is engineered to run indefinitely as a local service, implementing strict fault-tolerance mechanisms.

### Path Safety and iCloud Deadlocks
macOS heavily protects Desktop, Documents, and iCloud paths.
- The `install.sh` script validates write permissions before scaffolding.
- **Resource Deadlock Avoidance:** Syncing files via iCloud often causes file locks. The daemon strictly avoids high-level syscalls like `shutil.copy` on incoming files. It utilizes a polling loop (`st_size > 0`), delays, and `unlink(missing_ok=True)` fallbacks with retry logic to ensure the daemon doesn't crash on locked files.

### Failure Handling
To prevent infinite retry loops that drain API credits, if a file causes a JSON parse error or an API failure, it is caught by a `try/except` block and immediately moved to the `failed/` directory with a timestamp.

### Redaction and Logging
- All Google API usage is extracted (`response.usage_metadata`) and appended to `logs/cost_tracker.jsonl` for deterministic cost auditing.
- A custom `APIRedactingFormatter` intercepts all output within the Python `logging` module, ensuring the user's `GEMINI_API_KEY` is completely scrubbed from disk logs (`daemon.log`, `linter.log`) and standard output streams.
- The logs use `RotatingFileHandler` constrained to 5MB, maintaining a small, deterministic disk footprint.

### System Integration
- The application relies on native macOS `launchctl` to keep the background daemon alive (`KeepAlive = true`).
- Push notifications are dispatched natively via AppleScript (`osascript`). To prevent command injection vulnerabilities, variables are passed securely as positional command-line arguments (`argv`), not via string interpolation.
