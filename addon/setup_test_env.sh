#!/bin/bash
# Setup script for local testing
# Usage: bash setup_test_env.sh

set -e

ADDON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ADDON_DIR/.venv"

echo "🚀 Setting up test environment..."
echo ""

# Create virtual environment
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Activate venv
echo "✅ Activating virtual environment..."
source "$VENV_DIR/bin/activate"

# Install dependencies
echo "📥 Installing dependencies..."
pip install -q -r backend/requirements.txt
pip install -q pytest

echo ""
echo "✅ Setup complete!"
echo ""
echo "To run tests:"
echo "  source $VENV_DIR/bin/activate"
echo "  python backend/test_irrigation.py"
echo "  # or with pytest:"
echo "  pytest backend/test_irrigation.py -v"
echo ""
echo "To use Docker environment:"
echo "  docker-compose -f docker-compose.test.yml up"
echo ""
