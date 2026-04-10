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
    CLEANED_VAULT_PATH = VAULT_PATH_RAW.replace("\\ ", " ").replace("\\~", "~").replace('\\"', '"').replace("\\'", "'")

    vault_dir = Path(CLEANED_VAULT_PATH).expanduser().resolve()
    wiki_dir = vault_dir / "wiki"

    if not wiki_dir.exists():
        logging.warning("Wiki directory does not exist. Graph will be empty.")
        return

    nodes = []
    links = []

    existing_files = set()

    # First pass: Identify all existing files
    for root, _, files in os.walk(wiki_dir):
        for file in files:
            if file.endswith(".md"):
                # Use filename without extension as ID for easy matching with wikilinks
                file_id = file[:-3]
                existing_files.add(file_id)

                # Determine group based on parent directory
                parent_dir = Path(root).name
                group = "entity" if parent_dir == "entities" else "concept"

                nodes.append({
                    "id": file_id,
                    "group": group
                })

    # Regex to find [[Wikilinks]] or [[Wikilink|Alias]]
    wikilink_pattern = re.compile(r"\[\[(.*?)\]\]")

    ghost_nodes = set()

    # Second pass: Extract links
    for root, _, files in os.walk(wiki_dir):
        for file in files:
            if file.endswith(".md"):
                source_id = file[:-3]
                file_path = Path(root) / file

                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    matches = wikilink_pattern.findall(content)
                    for match in matches:
                        # Handle aliases: [[Target|Display]] -> Target
                        target = match.split("|")[0].strip()

                        # Add link
                        links.append({
                            "source": source_id,
                            "target": target
                        })

                        # Create ghost node if target doesn't exist and we haven't added it yet
                        if target not in existing_files and target not in ghost_nodes:
                            ghost_nodes.add(target)
                            nodes.append({
                                "id": target,
                                "group": "ghost"
                            })

                except Exception as e:
                    logging.error(f"Error reading file for graph generation: {file_path}. Error: {e}")

    graph_data = {
        "nodes": nodes,
        "links": links
    }

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
