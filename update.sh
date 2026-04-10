#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
cd "$SCRIPT_DIR"

echo "Pulling latest changes from Git..."
git pull

echo "Re-running installer to update dependencies and reload services..."
./install.sh

echo "Daemon.md successfully updated!"
