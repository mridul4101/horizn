#!/usr/bin/env bash
# reset.sh – Reset Horizn database and exported photos for a fresh run from scratch.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "⚠️  This will reset your local Horizn database and export cache."
echo "   (Your original photos and .env configuration will NOT be affected)."

read -r -p "Are you sure you want to proceed? [y/N] " response

if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
    rm -f data/horizn.db*
    rm -rf data/exports/*
    mkdir -p data/exports
    echo "✨ Horizn has been reset to a fresh state!"
    echo "   Start the service with ./scripts/start.sh and sync your photos."
else
    echo "Reset aborted."
fi
