#!/usr/bin/env bash
# refresh_token.sh – Refresh the Instagram long-lived access token.
# Intended to be run monthly via cron:
#   0 9 1 * * /Users/<you>/horizn/scripts/refresh_token.sh >> /tmp/horizn_token_refresh.log 2>&1
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# shellcheck disable=SC1091
source .venv/bin/activate

# shellcheck disable=SC1091
set -o allexport; source .env; set +o allexport

python3 -c "
import asyncio
from horizn.publisher.token_refresh import refresh_token
asyncio.run(refresh_token())
"
