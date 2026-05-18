#!/bin/bash
# Shopbot — one-command startup

set -e
cd "$(dirname "$0")"

echo "🔶 Shopbot — Starting…"

# Find a compatible Python version (prefer stable 3.12/3.11/3.10; allow 3.13/3.14 as fallback)
PYTHON_CMD="python3"
for cmd in python3.12 python3.11 python3.10 python3.13 python3.14; do
  if command -v $cmd &>/dev/null; then
    PYTHON_CMD=$cmd
    break
  fi
done

# Create venv if not present
if [ ! -d "venv" ]; then
  echo "📦 Creating virtual environment using $PYTHON_CMD…"
  $PYTHON_CMD -m venv venv
fi

# Activate
source venv/bin/activate

# Install dependencies
echo "📦 Installing backend dependencies…"
pip install -q -r backend/requirements.txt

# Install Playwright browsers (idempotent)
echo "🌐 Checking Playwright browsers…"
playwright install chromium --with-deps 2>/dev/null || true

# Copy .env if missing
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
  cp .env.example .env
  echo "⚠️  Created .env from .env.example — edit it to add Telegram credentials if needed."
fi

echo ""
echo "✅ Shopbot is running at http://localhost:8000"
echo "   Press Ctrl+C to stop."
echo ""

# Start server
# NOTE: --reload is for development only; remove it (and change host to 127.0.0.1) for production
cd backend
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
