#!/usr/bin/env bash
# Bhuvana's Pit Wall — start script (Mac / Linux)
# Usage: ./start.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "🏎  Bhuvana's Pit Wall — setup check"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check Python 3
if ! command -v python3 &>/dev/null; then
  echo "  ✗ python3 not found. Install it from https://python.org"
  exit 1
fi

PYTHON=$(command -v python3)
echo "  ✓ Python: $($PYTHON --version)"

# Install / upgrade deps
echo "  ↳ Installing dependencies…"
"$PYTHON" -m pip install -q -r requirements.txt

echo ""
echo "  Opening dashboard at http://localhost:5000 once server starts…"
echo ""

# Open browser after a short delay (background)
(sleep 3 && open "http://localhost:5000" 2>/dev/null || xdg-open "http://localhost:5000" 2>/dev/null || true) &

# Run server
exec "$PYTHON" server.py
