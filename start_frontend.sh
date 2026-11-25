#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-3000}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

echo "Starting Vocalyx frontend at http://localhost:${PORT}"
echo "Note: Open http://localhost:${PORT} (keep 'localhost' so Chrome microphone/speech recognition works)."
echo "First time on localhost, go to Settings -> paste your Kaggle ngrok URL -> Connect."

exec python3 -u -m http.server "$PORT" --bind 127.0.0.1 --directory "$FRONTEND_DIR"
