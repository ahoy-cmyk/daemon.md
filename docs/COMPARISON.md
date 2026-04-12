# System Comparison: Daemon.md vs. Karpathy's "LLM Wiki" Proposal

Daemon.md was directly inspired by Andrej Karpathy's ["LLM Wiki" concept](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). This document outlines the core agreements between the two architectures and details the specific engineering improvements Daemon.md introduces to operationalize the pattern for local, continuous usage.

## Core Agreements: The Foundational Philosophy

Daemon.md adopts the fundamental premises outlined in Karpathy's proposal, moving away from stateless Retrieval-Augmented Generation (RAG) toward a persistent, compiled knowledge base.

1. **Eager Compilation over RAG**
   RAG systems retrieve relevant chunks of raw data at query time, meaning the LLM must rediscover knowledge and synthesize it from scratch for every question. Both systems agree that knowledge should be "compiled" at ingestion time. The LLM reads the source once, extracts key information, and permanently integrates it into existing, structured markdown files.
2. **The Persistent Wiki as the Intermediate Layer**
   The knowledge base acts as a stateful artifact between the user and raw sources. The cross-references are pre-calculated, contradictions are flagged, and summaries are updated incrementally. The wiki is a directory of LLM-generated markdown files that humans read and the LLM writes.
3. **LLM as the Maintainer**
   The tedious bookkeeping required to maintain a knowledge base (updating cross-references, maintaining consistency, organizing files) is offloaded entirely to the LLM. The user focuses on providing sources, thinking, and asking questions.
4. **Separation of Raw Data and Compiled Output**
   Raw sources are treated as immutable truth. The system reads from raw files but never alters them, separating the immutable source material from the LLM-owned compiled wiki.
5. **Schema-Driven Behavior**
   Both systems utilize a configuration schema (`GEMINI.md` in Daemon.md) to define conventions, directory structures, and workflows for the LLM to follow, ensuring disciplined maintenance rather than generic chatbot behavior.

---

## Architectural Improvements in Daemon.md

While the Karpathy proposal outlines a theoretical pattern and suggests CLI tools or manual orchestration, Daemon.md provides a concrete, automated, and continuous background implementation.

### 1. Continuous Background Execution vs. Manual Ingestion
- **Proposal:** Suggests manually dropping files and telling the LLM to process them via a chat interface or CLI.
- **Daemon.md:** Implements a continuous background service (`daemon.py`) using `watchdog` and polling fallbacks (`DAEMON_POLL_INTERVAL`). When a file is dropped into the `raw/` directory, the daemon automatically wakes up, processes it, updates the wiki, and sends a native macOS push notification upon completion. This removes the need for human-in-the-loop orchestration for basic ingestion.

### 2. Context Optimization via Latent Space Mapping
- **Proposal:** Relies on an `index.md` catalog for the LLM to navigate the wiki before drilling into specific pages.
- **Daemon.md:** Implements `graph_builder.py`, which deterministically generates a `latent_space.json` map of the entire vault after every ingestion. This map provides a lightweight structural overview of all nodes (files) and edges (wikilinks), including "Ghost Nodes" (links to concepts that don't exist yet). The daemon feeds this JSON to the LLM instead of the entire text of the vault, significantly reducing token consumption and context window pressure while maintaining a global structural view.

### 3. The Self-Feedback Loop (Capturing Manual Edits)
- **Proposal:** Assumes the LLM entirely owns the wiki layer and the user mostly reads it.
- **Daemon.md:** Recognizes that users will inevitably edit the generated markdown to fix typos or add thoughts. A `WikiFolderHandler` actively monitors the `wiki/` directory. If a human edits a file (verified by tracking the daemon's own disk writes), it automatically copies the modified file back to the `raw/` inbox with a `manual_edit_` prefix. The AI ingests this edit, formalizing the human's input into the overall knowledge graph.

### 4. Archiving and Full System Rebuilds
- **Proposal:** Mentions keeping raw sources as immutable files but doesn't prescribe a system-wide versioning strategy across LLM model upgrades.
- **Daemon.md:** Moves processed files from `raw/` to `archive/` rather than deleting them. This establishes an unindexed source of truth. The `rebuild.py` script allows users to clear the generated wiki and feed the entire archive back through the system. This enables users to retroactively upgrade their entire knowledge base when newer, more capable LLMs are released, ensuring the data is not locked to the intelligence of a specific point in time.

### 5. Automated System Maintenance (Synthesis Linter)
- **Proposal:** Suggests periodically asking the LLM to lint the wiki for contradictions, orphans, and gaps.
- **Daemon.md:** Automates this via `lint_wiki.py`, designed to run as a scheduled cron job. It packages the vault content and prompts a reasoning model (e.g., `gemini-3.1-pro-preview`) to audit the graph. It automatically outputs a `Maintenance_Report.md` detailing contradictions and structural issues, ensuring the maintenance burden remains near zero.

### 6. Native Audio Processing
- **Proposal:** Focuses primarily on text, web clippings, and images.
- **Daemon.md:** Natively supports audio ingestion (`.m4a`, `.mp3`, `.wav`) by uploading media directly to the Gemini API for transcription and analysis. It securely handles the file lifecycle, ensuring remote files are explicitly deleted after processing to prevent storage leaks and quota exhaustion.

### 7. Native OS Integration and Lifecycle Control
- **Proposal:** Assumes the user is either manually running scripts in the terminal or wiring up an agent orchestrator.
- **Daemon.md:** Hooks directly into macOS via `launchd` and property list (`.plist`) files generated by `install.sh`. The ingestion engine (`daemon.py`) runs as a persistent background daemon, and the synthesis linter (`lint_wiki.py`) runs as a cron job (defaulting to Sunday at 3 AM). Users maintain total control over the lifecycle via included shell scripts without having to remember terminal commands:
  - `./status.sh` reports if the `launchd` services are running, displays token usage/cost, and tails the latest logs.
  - `./uninstall.sh` instantly unloads and removes the background services.
  - `./update.sh` pulls the latest code and safely restarts the processes.

## Conclusion

Daemon.md fully embraces the LLM Wiki philosophy but focuses on removing the friction of manual operation. By implementing a continuous background daemon, structured context mapping, human-in-the-loop feedback, and deterministic archiving, it transforms the "LLM Wiki" concept from an interactive prompt pattern into an autonomous, locally-running knowledge engine.
