import os
import json
import re
import logging
from pathlib import Path
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).parent.resolve()
load_dotenv(SCRIPT_DIR / ".env")

VAULT_PATH_RAW = os.getenv("VAULT_PATH")
VISUALIZER_PUBLIC_DIR = SCRIPT_DIR / "visualizer" / "public"


def build_graph():
    """Generates a node/edge graph from the wiki directory."""
    if not VAULT_PATH_RAW:
        logging.error("VAULT_PATH not set in .env. Cannot build graph.")
        return

    # Clean terminal escape characters
    CLEANED_VAULT_PATH = (
        VAULT_PATH_RAW.replace("\\ ", " ")
        .replace("\\~", "~")
        .replace('\\"', '"')
        .replace("\\'", "'")
    )

    vault_dir = Path(CLEANED_VAULT_PATH).expanduser().resolve()
    wiki_dir = vault_dir / "wiki"

    if not wiki_dir.exists():
        logging.warning("Wiki directory does not exist. Graph will be empty.")
        return

    nodes = []
    links = []

    existing_files = set()
    file_contents = {}

    # Regex to find [[Wikilinks]] or [[Wikilink|Alias]]
    wikilink_pattern = re.compile(r"\[\[(.*?)\]\]")

    # Single pass: Identify files, map them, and read contents
    for root, _, files in os.walk(wiki_dir):
        for file in files:
            if file.endswith(".md"):
                file_id = file[:-3]
                existing_files.add(file_id)
                file_path = Path(root) / file

                # Determine group based on parent directory
                parent_dir = Path(root).name
                group = "entity" if parent_dir == "entities" else "concept"

                # Get timeline metadata
                try:
                    stat = file_path.stat()
                    ctime = int(stat.st_ctime)
                    mtime = int(stat.st_mtime)
                except Exception:
                    ctime = 0
                    mtime = 0

                content = ""
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        file_contents[file_id] = content

                        # Try to extract permanent timeline metadata from YAML frontmatter
                        import datetime

                        match_c = re.search(
                            r"^---\n.*?created_at:\s*[\"']?(.*?)[\"']?\n",
                            content,
                            re.DOTALL,
                        )
                        if match_c:
                            dt_c = datetime.datetime.fromisoformat(
                                match_c.group(1).replace("Z", "+00:00")
                            )
                            ctime = int(dt_c.timestamp())

                        match_m = re.search(
                            r"^---\n.*?updated_at:\s*[\"']?(.*?)[\"']?\n",
                            content,
                            re.DOTALL,
                        )
                        if match_m:
                            dt_m = datetime.datetime.fromisoformat(
                                match_m.group(1).replace("Z", "+00:00")
                            )
                            mtime = int(dt_m.timestamp())

                except Exception as e:
                    logging.error(
                        f"Error reading file for graph generation: {file_path}. Error: {e}"
                    )
                    file_contents[file_id] = ""

                nodes.append(
                    {
                        "id": file_id,
                        "group": group,
                        "created_at": ctime,
                        "modified_at": mtime,
                    }
                )

    ghost_nodes = set()

    # Process links from the memory-cached contents
    for source_id, content in file_contents.items():
        matches = wikilink_pattern.findall(content)
        for match in matches:
            # Handle aliases: [[Target|Display]] -> Target
            target = match.split("|")[0].strip()

            # Add link
            links.append({"source": source_id, "target": target})

            # Create ghost node if target doesn't exist and we haven't added it yet
            if target not in existing_files and target not in ghost_nodes:
                ghost_nodes.add(target)
                nodes.append({"id": target, "group": "ghost"})

    graph_data = {"nodes": nodes, "links": links}

    # Ensure output directory exists
    VISUALIZER_PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

    output_path = VISUALIZER_PUBLIC_DIR / "latent_space.json"

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(graph_data, f, indent=2)
        logging.info(f"Successfully generated graph data at {output_path}")
    except Exception as e:
        logging.error(f"Failed to write graph data to {output_path}: {e}")


if __name__ == "__main__":
    # Configure basic logging for standalone execution
    logging.basicConfig(level=logging.INFO)
    build_graph()
