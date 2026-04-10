#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
cd "$SCRIPT_DIR/visualizer"

echo "Starting Latent Space Explorer..."
echo "Open http://localhost:5173 in your browser"

npm run dev
