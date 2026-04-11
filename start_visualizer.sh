#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
cd "$SCRIPT_DIR/visualizer"

echo "Starting Latent Space Explorer..."
echo "Opening http://localhost:5173 in your browser..."

# Open the browser in the background
open http://localhost:5173 &

npm run dev
