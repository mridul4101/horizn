#!/usr/bin/env bash
# setup.sh – One-time environment bootstrap for Horizn.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# ---------------------------------------------------------------------------
# 1. Check prerequisites
# ---------------------------------------------------------------------------
echo "🔍  Checking prerequisites…"

python_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
required_python="3.11"
if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"; then
    echo "  ✅  Python $python_version"
else
    echo "  ❌  Python >= $required_python required (found $python_version)" >&2
    exit 1
fi

node_version=$(node --version 2>/dev/null || echo "none")
if [[ "$node_version" == "none" ]]; then
    echo "  ❌  Node.js not found. Install Node >= 18 via https://nodejs.org" >&2
    exit 1
fi
node_major=$(echo "$node_version" | sed 's/v\([0-9]*\).*/\1/')
if [[ "$node_major" -lt 18 ]]; then
    echo "  ❌  Node >= 18 required (found $node_version)" >&2
    exit 1
fi
echo "  ✅  Node $node_version"

# ---------------------------------------------------------------------------
# 2. Create Python virtual environment
# ---------------------------------------------------------------------------
if [[ ! -d ".venv" ]]; then
    echo "🐍  Creating virtual environment at .venv…"
    python3 -m venv .venv
fi

# ---------------------------------------------------------------------------
# 3. Install Python package (editable)
# ---------------------------------------------------------------------------
echo "📦  Installing Python dependencies…"
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip --quiet
pip install -e ".[dev]" --quiet
echo "  ✅  Python packages installed"

# ---------------------------------------------------------------------------
# 4. Install Node dependencies (UI)
# ---------------------------------------------------------------------------
if [[ -f "ui/package.json" ]]; then
    echo "🌐  Installing Node dependencies in ui/…"
    npm install --prefix ui
    echo "  ✅  Node packages installed"
else
    echo "  ⚠️   ui/package.json not found – skipping npm install (run after Worker 3 creates the UI)"
fi

# ---------------------------------------------------------------------------
# 5. Copy .env.example → .env
# ---------------------------------------------------------------------------
if [[ ! -f ".env" ]]; then
    echo "🔑  Copying .env.example → .env"
    cp .env.example .env
    echo "  ✅  .env created – fill in your secrets before running Horizn"
else
    echo "  ℹ️   .env already exists – skipping copy"
fi

# ---------------------------------------------------------------------------
# 6. Initialise database
# ---------------------------------------------------------------------------
echo "🗄️   Initialising SQLite database…"
python3 -c "import asyncio; from horizn.database import init_db; asyncio.run(init_db())"
echo "  ✅  Database ready at data/horizn.db"

# ---------------------------------------------------------------------------
# 7. Done
# ---------------------------------------------------------------------------
echo ""
echo "✨  Horizn setup complete!"
echo "    Edit .env with your API keys, then run:  ./scripts/start.sh"
